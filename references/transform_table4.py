#!/usr/bin/env python3
"""
transform_table4.py

Reads TABLE1 (invoice level) and TABLE4 (bag level) from CSV.
Resolves semicolon-delimited invoice ID cells in TABLE4 by splitting
into individual IDs, recalculating charges from first principles,
and outputting a clean TABLE4 and a reconciliation summary.

Usage:
    python transform_table4.py [--table1 table1.csv] [--table4 table4.csv]
                               [--out-table4 table4_transformed.csv]
                               [--out-recon reconciliation.csv]
                               [--log transform.log]
"""

import argparse
import logging
import math
import sys

import pandas as pd

# ---------------------------------------------------------------------------
# Tonnage denominator column names
# ---------------------------------------------------------------------------
MINE_GROSS_T1 = 'DRC DATA - PUDA GROSS WT EXCL. SAMPLE (KG)'
PORT_GROSS_T1 = 'PORT WHS GROSS WEIGHT (KG)'
PORT_NET_T1   = 'PORT WHS NET WEIGHT (KG)'

MINE_GROSS_T4 = 'PUDA GROSS WT EXCL. SAMPLE (TONS)'
PORT_GROSS_T4 = 'PORT WAREHOUSE GROSS WEIGHT (TONS)'
PORT_NET_T4   = 'PORT WAREHOUSE NET WEIGHT (TONS)'

# ---------------------------------------------------------------------------
# Category configuration — 23 invoice ID / charge column pairs (TABLE4 order)
# ---------------------------------------------------------------------------
# t1_ton_div: all TABLE1 tonnage columns are in KG; divide by 1000 to get tonnes
# t1_ton_div      → all TABLE1 tonnage columns are in KG; divide by 1000

CATEGORY_CONFIG = [
    {
        'label':         'Inland Transportation (Total)',
        'display_label': 'Inland Transportation (Total)',
        'inv_id_col': 'INLAND TRANSPORTATION INVOICE ID.',
        'charge_col': 'TOTAL INLAND (BASE & FUEL CHARGE) ($)',
        't1_charge':  'TOTAL INLAND (BASE & FUEL) ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Other Inland Transport',
        'display_label': 'Other Inland Costs',
        'inv_id_col': 'OTHER INLAND TRANSPORT INVOICE ID.',
        'charge_col': 'OTHER INLAND TRANSPORT CHARGE ($)',
        't1_charge':  'OTHER INLAND TRANSPORT ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Performance Bonus',
        'display_label': 'Performance Bonus',
        'inv_id_col': 'PERFORMANCE BONUS INVOICE ID',   # NOTE: no trailing period
        'charge_col': 'PERFORMANCE BONUS CHARGE ($)',
        't1_charge':  'PERFORMANCE BONUS CHARGE ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Demurrage (Truck)',
        'display_label': 'Demurrage (Truck)',
        'inv_id_col':    'DEMURRAGE TRUCK INVOICE ID.',
        'charge_col':    'DEMURRAGE TRUCK CHARGE ($)',
        't1_charge':     'DEMURRAGE TRUCK ($)',
        't1_tonnage':    MINE_GROSS_T1,
        't1_ton_div':    1000,
        't4_tonnage':    MINE_GROSS_T4,
        'recalc_method': 'per_bag',
    },
    {
        'label':         'Demurrage (Truck-Other)',
        'display_label': 'Demurrage (Truck - Other)',
        'inv_id_col':    'DEMURRAGE OTHER INVOICE ID.',
        'charge_col':    'DEMURRAGE TRUCK OTHER CHARGE ($)',
        't1_charge':     'DEMURRAGE TRUCK OTHER ($)',
        't1_tonnage':    MINE_GROSS_T1,
        't1_ton_div':    1000,
        't4_tonnage':    MINE_GROSS_T4,
        'recalc_method': 'per_bag',
    },
    {
        'label':         'Reception Logistics',
        'display_label': 'Logistics Reception Costs',
        'inv_id_col': 'RECEPTION LOGISTICS INVOICE ID.',
        'charge_col': 'RECEPTION LOGISTICS CHARGE ($)',
        't1_charge':  'RECEPTION LOGISTICS ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Assay - Reception Related',
        'display_label': 'Assay / Environmental / Courier - On Reception',
        'inv_id_col': 'ASSAY - RECEPTION RELATED INVOICE ID.',
        'charge_col': 'ASSAY RECEPTION RELATED CHARGE ($)',
        't1_charge':  'ASSAY - RECEPTION RELATED ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Sampling & Weighing',
        'display_label': 'Sampling and Weighing',
        'inv_id_col': 'WSMD (RECEPTION) INVOICE ID.',
        'charge_col': 'WSMD (RECEPTION) ($)',
        't1_charge':  'SAMPLING WEIGHING ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Other WSMD',
        'display_label': 'Other WSMD Costs',
        'inv_id_col': 'OTHER WSMD INVOICE ID.',
        'charge_col': 'OTHER WSMD CHARGE ($)',
        't1_charge':  'OTHER WSMD ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Insurance DAP',
        'display_label': 'Insurance - DAP',
        'inv_id_col': 'INSURANCE DAP INVOICE ID.',
        'charge_col': 'INSURANCE DAP CHARGE ($)',
        't1_charge':  'INSURANCE DAP ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Insurance CIF',
        'display_label': 'Insurance - CIF',
        'inv_id_col': 'INSURANCE CIF INVOICE ID.',
        'charge_col': 'INSURANCE CIF CHARGE ($)',
        't1_charge':  'INSURANCE CIF ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Other Logistics (excl. Inland)',
        'display_label': 'Other Logistics Costs (excl. Inland)',
        'inv_id_col': 'OTHER LOGISTICS (EX. INLAND) INVOICE ID.',
        'charge_col': 'OTHER LOGISTICS (EX. INLAND) CHARGE ($)',
        't1_charge':  'OTHER LOGISTICS (EX. INLAND)  ($)',   # NOTE: two spaces before ($)
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'TML',
        'display_label': 'TML',
        'inv_id_col': 'TML INVOICE ID.',
        'charge_col': 'TML CHARGE ($)',
        't1_charge':  'TML ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Umpire Costs',
        'display_label': 'Umpire Costs',
        'inv_id_col': 'UMPIRE COST INVOICE ID.',
        'charge_col': 'UMPIRE CHARGE ($)',
        't1_charge':  'UMPIRE ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Ocean Freight',
        'display_label': 'Ocean Freight',
        'inv_id_col': 'OCEAN FREIGHT INVOICE ID.',
        'charge_col': 'OCEAN FREIGHT CHARGE ($)',
        't1_charge':  'OCEAN FREIGHT ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Dispatch',
        'display_label': 'Despatch (Vessel)',
        'inv_id_col': 'VESSEL DISPATCH INVOICE ID.',
        'charge_col': 'VESSEL DISPATCH CHARGE ($)',
        't1_charge':  'VESSEL DISPATCH ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Demurrage',
        'display_label': 'Demurrage (Vessel)',
        'inv_id_col': 'VESSEL DEMURRAGE INVOICE ID.',
        'charge_col': 'VESSEL DEMURRAGE CHARGE ($)',
        't1_charge':  'VESSEL DEMURRAGE ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         "FOB's",
        'display_label': "FOB's (incl. Overtime if incurred)",
        'inv_id_col': 'FOBs INVOICE ID.',
        'charge_col': 'FOBs CHARGE ($)',
        't1_charge':  'FOBs ($)',
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'Port WHS Storage',
        'display_label': 'Port Warehouse Storage',
        'inv_id_col': 'PORT WHS STORAGE INVOICE ID',   # NOTE: no trailing period
        'charge_col': 'PORT WHS STORAGE CHARGE ($)',
        't1_charge':  'PORT WHS STORAGE ($)',
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'Draft Survey',
        'display_label': 'Draft Survey',
        'inv_id_col': 'DRAFT SURVEY INVOICE ID.',
        'charge_col': 'DRAFT SURVERY CHARGE ($)',      # NOTE: typo in source — preserved
        't1_charge':  'DRAFT SURVEY ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Load Supervision',
        'display_label': 'Vessel Load Supervision',
        'inv_id_col': 'VESSEL LOAD SUPERVISION INVOICE ID.',
        'charge_col': 'VESSEL LOAD SUPERVISION CHARGE ($)',
        't1_charge':  'VESSEL LOAD SUPERVISION ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Discharge Supervision',
        'display_label': 'Vessel Discharge Supervision',
        'inv_id_col': 'VESSEL DISCHARGE SUPERVISION INVOICE ID.',
        'charge_col': 'VESSEL DISCHARGE SUPERVISION CHARGE ($)',
        't1_charge':  'VESSEL DISCHARGE SUPERVISION ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Assay - Vessel Related',
        'display_label': 'Assay / Environmental / Courier - Vessel Related',
        'inv_id_col': 'ASSAY - VESSEL RELATED INVOICE ID.',
        'charge_col': 'ASSAY VESSEL RELATED CHARGE ($)',
        't1_charge':  'ASSAY - VESSEL RELATED ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
]

# ---------------------------------------------------------------------------
# TABLE1 columns that need numeric conversion
# ---------------------------------------------------------------------------
T1_CHARGE_COLS = [
    'BASE FREIGHT CHARGE ($)',
    'FUEL SURCHARGE CHARGE ($)',
    'OTHER INLAND TRANSPORT ($)',
    'PERFORMANCE BONUS CHARGE ($)',
    'DEMURRAGE TRUCK ($)',
    'DEMURRAGE TRUCK OTHER ($)',
    'RECEPTION LOGISTICS ($)',
    'ASSAY - RECEPTION RELATED ($)',
    'SAMPLING WEIGHING ($)',
    'OTHER WSMD ($)',
    'INSURANCE DAP ($)',
    'INSURANCE CIF ($)',
    'OTHER LOGISTICS (EX. INLAND)  ($)',   # two spaces
    'TML ($)',
    'UMPIRE ($)',
    'OCEAN FREIGHT ($)',
    'VESSEL DISPATCH ($)',
    'VESSEL DEMURRAGE ($)',
    'FOBs ($)',
    'PORT WHS STORAGE ($)',
    'DRAFT SURVEY ($)',
    'VESSEL LOAD SUPERVISION ($)',
    'VESSEL DISCHARGE SUPERVISION ($)',
    'ASSAY - VESSEL RELATED ($)',
    'TOTAL INLAND (BASE & FUEL) ($)',
    'INVOICE AMOUNT.2',
]

T1_WEIGHT_COLS = [
    'DRC DATA - PUDA GROSS WT EXCL. SAMPLE (KG)',
    'PORT WHS GROSS WEIGHT (KG)',
    'PORT WHS NET WEIGHT (KG)',
]

T4_WEIGHT_COLS = [
    'PUDA GROSS WT EXCL. SAMPLE (TONS)',
    'PORT WAREHOUSE GROSS WEIGHT (TONS)',
    'PORT WAREHOUSE NET WEIGHT (TONS)',
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def safe_float(val, default=0.0):
    """Convert val to float; return default on NaN / conversion error."""
    try:
        f = float(val)
        return default if math.isnan(f) else f
    except (ValueError, TypeError):
        return default


def clean_id(val):
    """Strip whitespace and uppercase a value; return '' for empty/nan."""
    s = str(val).strip()
    return s.upper() if s and s.lower() != 'nan' else ''


def split_ids(val):
    """Split a possibly semicolon-delimited string into a list of clean IDs."""
    return [cid for cid in (clean_id(x) for x in str(val).split(';')) if cid]


def clean_str(val):
    """Stringify, strip, and return '' for nan-like values."""
    s = str(val).strip()
    return '' if s.lower() == 'nan' else s


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description='Transform TABLE4 — resolve semicolon invoice IDs and recalculate charges.'
    )
    parser.add_argument('--table1',     default='INVOICE - COST ALLOCATION - TABLE 1.csv',
                        help='Path to TABLE1 CSV')
    parser.add_argument('--table4',     default='BAG - COST ALLOCATION - TABLE 4.csv',
                        help='Path to TABLE4 CSV')
    parser.add_argument('--out-table4', default='table4_transformed.csv',
                        help='Output transformed TABLE4 CSV (default: table4_transformed.csv)')
    parser.add_argument('--out-recon',  default='reconciliation.csv',
                        help='Output reconciliation CSV (default: reconciliation.csv)')
    parser.add_argument('--log',        default='transform.log',
                        help='Log file path (default: transform.log)')
    parser.add_argument('--full-recalc', action='store_true',
                        help='Recalculate ALL bag charges from TABLE1, including single-invoice rows '
                             '(one-off mode; default: only semicolon rows are recalculated)')
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Logging — file + stdout
    # ------------------------------------------------------------------
    logging.basicConfig(
        level=logging.INFO,
        format='%(levelname)s: %(message)s',
        handlers=[
            logging.FileHandler(args.log, mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout),
        ],
    )
    log = logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Step 1 — Load data (all columns as string; convert numeric after)
    # ------------------------------------------------------------------
    log.info(f'Loading TABLE1: {args.table1}')
    t1 = pd.read_csv(args.table1, dtype=str)

    log.info(f'Loading TABLE4: {args.table4}')
    t4 = pd.read_csv(args.table4, dtype=str)

    rows_in = len(t4)
    log.info(f'TABLE1: {len(t1)} rows  |  TABLE4: {rows_in} rows')

    # Convert TABLE1 numeric columns
    for col in T1_CHARGE_COLS + T1_WEIGHT_COLS:
        if col in t1.columns:
            t1[col] = pd.to_numeric(t1[col], errors='coerce')
        else:
            log.warning(f'TABLE1 missing expected column: {col!r}')

    # Convert TABLE4 charge and weight columns
    t4_charge_cols = [cfg['charge_col'] for cfg in CATEGORY_CONFIG]
    for col in t4_charge_cols + T4_WEIGHT_COLS:
        if col in t4.columns:
            t4[col] = pd.to_numeric(t4[col], errors='coerce').astype('float64')
        else:
            log.warning(f'TABLE4 missing expected column: {col!r}')

    # ------------------------------------------------------------------
    # Step 2 — Build TABLE1 invoice lookup  {INVOICE_ID (upper) -> row}
    # ------------------------------------------------------------------
    t1['_inv_key'] = t1['INVOICE ID.'].astype(str).str.strip().str.upper()
    dup_mask = t1['_inv_key'].duplicated(keep=False) & (t1['_inv_key'] != '') & (t1['_inv_key'].str.lower() != 'NAN')
    dup_ids  = t1.loc[dup_mask, '_inv_key'].unique().tolist()
    if dup_ids:
        log.warning(
            f'Duplicate INVOICE ID. values in TABLE1 (last row used): '
            f'{sorted(dup_ids)}'
        )
    inv_lookup = {
        row['_inv_key']: row
        for _, row in t1.iterrows()
        if row['_inv_key'] and row['_inv_key'].lower() != 'nan'
    }
    t1.drop(columns=['_inv_key'], inplace=True)
    log.info(f'TABLE1 lookup built: {len(inv_lookup)} unique invoice IDs')

    # ------------------------------------------------------------------
    # Step 3 — Pre-scan: find max number of semicolon-delimited IDs per
    #          category column (determines how many overflow columns needed)
    # ------------------------------------------------------------------
    max_ids = {}   # inv_id_col -> max count of IDs in any single cell
    for cfg in CATEGORY_CONFIG:
        inv_col = cfg['inv_id_col']
        if cfg.get('skip_recalc'):
            # Derived column — always take first ID only; no overflow needed
            max_ids[inv_col] = 1
            continue
        if inv_col not in t4.columns:
            max_ids[inv_col] = 1
            continue
        col_max = 1
        for val in t4[inv_col]:
            col_max = max(col_max, len(split_ids(val)))
        max_ids[inv_col] = col_max
        if col_max > 1:
            log.info(
                f'Category {cfg["label"]!r}: max {col_max} IDs in one cell '
                f'({col_max - 1} overflow column(s) will be added)'
            )

    # ------------------------------------------------------------------
    # Count semicolon cells BEFORE transformation
    # ------------------------------------------------------------------
    semicolon_before = 0
    for cfg in CATEGORY_CONFIG:
        inv_col = cfg['inv_id_col']
        if inv_col in t4.columns:
            semicolon_before += int(t4[inv_col].astype(str).str.contains(';').sum())
    log.info(f'Semicolon cells BEFORE transformation: {semicolon_before}')

    # ------------------------------------------------------------------
    # Step 4 — Add overflow columns and reorder so each overflow pair
    #          sits immediately after its parent (inv_col, charge_col)
    # ------------------------------------------------------------------
    original_columns = list(t4.columns)   # snapshot before appending

    # Append overflow columns to t4
    for cfg in CATEGORY_CONFIG:
        if cfg.get('skip_recalc'):
            continue
        inv_col = cfg['inv_id_col']
        chg_col = cfg['charge_col']
        n = max_ids.get(inv_col, 1)
        for i in range(2, n + 1):
            suffix  = f'_{i}'
            ov_inv  = inv_col + suffix
            ov_chg  = chg_col + suffix
            if ov_inv not in t4.columns:
                t4[ov_inv] = ''
            if ov_chg not in t4.columns:
                t4[ov_chg] = float('nan')

    # Build ordered column list.
    # The actual TABLE4 layout has all charge columns first, then all invoice ID
    # columns.  Respect this structure: insert overflow charge columns right after
    # their parent charge column, and overflow invoice ID columns right after their
    # parent invoice ID column.
    overflow_chg_cols = {}   # charge_col  -> [ov_chg_2, ov_chg_3, ...]
    overflow_inv_cols = {}   # inv_id_col  -> [ov_inv_2, ov_inv_3, ...]
    overflow_col_set  = set()
    for cfg in CATEGORY_CONFIG:
        if cfg.get('skip_recalc'):
            continue
        inv_col = cfg['inv_id_col']
        chg_col = cfg['charge_col']
        n = max_ids.get(inv_col, 1)
        chg_overflows = []
        inv_overflows = []
        for i in range(2, n + 1):
            suffix  = f'_{i}'
            ov_inv  = inv_col + suffix
            ov_chg  = chg_col + suffix
            chg_overflows.append(ov_chg)
            inv_overflows.append(ov_inv)
            overflow_col_set.add(ov_inv)
            overflow_col_set.add(ov_chg)
        overflow_chg_cols[chg_col] = chg_overflows
        overflow_inv_cols[inv_col] = inv_overflows

    ordered_cols = []
    for col in original_columns:
        ordered_cols.append(col)
        # After each charge_col: insert overflow charge columns
        if col in overflow_chg_cols:
            for ov_chg in overflow_chg_cols[col]:
                if ov_chg in t4.columns:
                    ordered_cols.append(ov_chg)
        # After each inv_id_col: insert overflow invoice ID columns
        if col in overflow_inv_cols:
            for ov_inv in overflow_inv_cols[col]:
                if ov_inv in t4.columns:
                    ordered_cols.append(ov_inv)

    # Safety net: include any columns not yet in the ordered list
    seen_cols = set(ordered_cols)
    for col in t4.columns:
        if col not in seen_cols:
            log.warning(f'Column not placed by ordering logic (appending at end): {col!r}')
            ordered_cols.append(col)
            seen_cols.add(col)

    t4 = t4[ordered_cols]

    # ------------------------------------------------------------------
    # Step 5 — Process each category
    # Vectorise where possible; only row-iterate over semicolon cells.
    # ------------------------------------------------------------------
    validation_bag_failures = []

    # Pre-compute bag counts per invoice ID for per_bag categories (demurrage).
    # Counts every bag (single + semicolon) that references each invoice ID.
    per_bag_counts = {}   # {inv_id_col: {inv_id: count}}
    for cfg in CATEGORY_CONFIG:
        if cfg.get('recalc_method') != 'per_bag':
            continue
        inv_col = cfg['inv_id_col']
        if inv_col not in t4.columns:
            continue
        counts = {}
        for raw_val in t4[inv_col].fillna('').astype(str):
            for inv_id in split_ids(raw_val.strip()):
                if inv_id:
                    counts[inv_id] = counts.get(inv_id, 0) + 1
        per_bag_counts[inv_col] = counts

    # Pre-compute T4 tonnage sums per invoice ID for rate × tonnage categories.
    # Rate denominator = sum of bag tonnages in T4 (not T1 invoice tonnage).
    # This ensures sum(rate × bag_tonnage) == invoice_amount regardless of
    # any T1 vs T4 weight discrepancies (e.g. bags with missing weight).
    t4_ton_sums = {}   # {inv_id_col: {inv_id: sum_of_t4_tonnage}}
    for cfg in CATEGORY_CONFIG:
        if cfg.get('recalc_method') == 'per_bag':
            continue
        inv_col = cfg['inv_id_col']
        t4_ton  = cfg['t4_tonnage']
        if inv_col not in t4.columns or t4_ton not in t4.columns:
            continue
        sums = {}
        id_series  = t4[inv_col].fillna('').astype(str)
        ton_series = pd.to_numeric(t4[t4_ton], errors='coerce').fillna(0.0)
        for raw_val, ton_val in zip(id_series, ton_series):
            for inv_id in split_ids(raw_val.strip()):
                if inv_id:
                    sums[inv_id] = sums.get(inv_id, 0.0) + ton_val
        t4_ton_sums[inv_col] = sums

    for cfg in CATEGORY_CONFIG:
        inv_col       = cfg['inv_id_col']
        chg_col       = cfg['charge_col']
        t1_chg        = cfg['t1_charge']
        t1_ton        = cfg['t1_tonnage']
        t1_div        = cfg['t1_ton_div']
        t4_ton        = cfg['t4_tonnage']
        label         = cfg['label']
        recalc_method = cfg.get('recalc_method')
        bag_counts    = per_bag_counts.get(inv_col, {})

        if inv_col not in t4.columns:
            log.warning(f'[{label}] Invoice ID column {inv_col!r} not in TABLE4 — skipping')
            continue

        # Build boolean masks once (vectorised)
        s_col     = t4[inv_col].astype(str).str.strip()
        valid_mask = s_col.notna() & (s_col != '') & (s_col.str.lower() != 'nan')
        semi_mask  = valid_mask & s_col.str.contains(';', regex=False)
        single_mask = valid_mask & ~semi_mask

        # Vectorised: normalise single-ID rows
        t4.loc[single_mask, inv_col] = s_col[single_mask].str.upper()

        # Row-iterate only the (small) set of semicolon rows
        semi_indices = t4.index[semi_mask].tolist()
        semi_count   = len(semi_indices)
        if semi_count:
            log.info(f'[{label}] Processing {semi_count} semicolon row(s)')

        for idx in semi_indices:
            raw = str(t4.at[idx, inv_col]).strip()
            ids = split_ids(raw)
            if not ids:
                continue

            bag_id          = clean_str(t4.at[idx, 'BAG ID']) if 'BAG ID' in t4.columns else str(idx)
            original_charge = safe_float(t4.at[idx, chg_col]) if chg_col in t4.columns else 0.0
            has_t4_ton      = t4_ton in t4.columns
            recalc_total    = 0.0

            for i, inv_id in enumerate(ids):
                if not inv_id:
                    continue

                if inv_id not in inv_lookup:
                    log.warning(
                        f'[{label}] BAG {bag_id}: invoice {inv_id!r} not found in '
                        f'TABLE1 — skipping this ID'
                    )
                    continue

                inv_row    = inv_lookup[inv_id]
                inv_amount = safe_float(
                    inv_row[t1_chg] if t1_chg in inv_row.index else float('nan')
                )

                if recalc_method == 'per_bag':
                    n_bags        = bag_counts.get(inv_id, 1)
                    recalc_charge = round(inv_amount / n_bags, 6)
                else:
                    inv_tonnage = t4_ton_sums.get(inv_col, {}).get(inv_id, 0.0)
                    bag_tonnage = safe_float(
                        t4.at[idx, t4_ton] if has_t4_ton else float('nan')
                    )
                    if inv_tonnage == 0:
                        log.warning(
                            f'[{label}] Invoice {inv_id}: zero T4 tonnage sum '
                            f'(col {t4_ton!r}) — charge forced to 0.0'
                        )
                        recalc_charge = 0.0
                    else:
                        rate          = inv_amount / inv_tonnage
                        recalc_charge = round(rate * bag_tonnage, 6)

                recalc_total += recalc_charge

                if i == 0:
                    t4.at[idx, inv_col] = inv_id
                    if chg_col in t4.columns:
                        t4.at[idx, chg_col] = recalc_charge
                else:
                    suffix = f'_{i + 1}'
                    ov_inv = inv_col + suffix
                    ov_chg = chg_col + suffix
                    if ov_inv in t4.columns:
                        t4.at[idx, ov_inv] = inv_id
                    else:
                        log.warning(
                            f'[{label}] BAG {bag_id}: overflow column {ov_inv!r} '
                            f'was not pre-created — data for invoice {inv_id} lost'
                        )
                    if ov_chg in t4.columns:
                        t4.at[idx, ov_chg] = recalc_charge
                    else:
                        log.warning(
                            f'[{label}] BAG {bag_id}: overflow column {ov_chg!r} '
                            f'was not pre-created — charge for invoice {inv_id} lost'
                        )

            # Validation 1: sum of per-invoice recalculated charges ≈ original
            if abs(recalc_total - original_charge) > 0.10:
                msg = (
                    f'[VALIDATION-BAG] [{label}] BAG {bag_id}: '
                    f'recalc sum {recalc_total:.6f} vs original {original_charge:.6f} '
                    f'(diff {abs(recalc_total - original_charge):.6f})'
                )
                log.warning(msg)
                validation_bag_failures.append(msg)

        # --full-recalc: recalculate single-invoice rows from TABLE1 as well
        if args.full_recalc:
            single_indices = t4.index[single_mask].tolist()
            if single_indices:
                log.info(f'[{label}] --full-recalc: recalculating {len(single_indices)} single-invoice row(s)')
            has_t4_ton = t4_ton in t4.columns
            for idx in single_indices:
                inv_id = s_col[idx].upper()
                if inv_id not in inv_lookup:
                    continue
                inv_row    = inv_lookup[inv_id]
                inv_amount = safe_float(
                    inv_row[t1_chg] if t1_chg in inv_row.index else float('nan')
                )
                if recalc_method == 'per_bag':
                    n_bags        = bag_counts.get(inv_id, 1)
                    recalc_charge = round(inv_amount / n_bags, 6)
                else:
                    inv_tonnage = t4_ton_sums.get(inv_col, {}).get(inv_id, 0.0)
                    bag_tonnage = safe_float(
                        t4.at[idx, t4_ton] if has_t4_ton else float('nan')
                    )
                    if inv_tonnage == 0:
                        recalc_charge = 0.0
                    else:
                        recalc_charge = round((inv_amount / inv_tonnage) * bag_tonnage, 6)
                if chg_col in t4.columns:
                    t4.at[idx, chg_col] = recalc_charge

    # ------------------------------------------------------------------
    # Step 6 — Count semicolon cells AFTER transformation
    # ------------------------------------------------------------------
    semicolon_after = 0
    for cfg in CATEGORY_CONFIG:
        inv_col = cfg['inv_id_col']
        if inv_col in t4.columns:
            semicolon_after += int(t4[inv_col].astype(str).str.contains(';').sum())
        n = max_ids.get(inv_col, 1)
        for i in range(2, n + 1):
            ov_col = inv_col + f'_{i}'
            if ov_col in t4.columns:
                semicolon_after += int(t4[ov_col].astype(str).str.contains(';').sum())

    log.info(f'Semicolon cells AFTER transformation: {semicolon_after}')
    if semicolon_after > 0:
        log.warning('Non-zero semicolon cells remain after transformation — investigate!')

    # ------------------------------------------------------------------
    # Step 7 — Output transformed TABLE4
    # ------------------------------------------------------------------
    rows_out = len(t4)
    log.info(f'Rows in: {rows_in}  |  Rows out: {rows_out}')
    if rows_in != rows_out:
        log.warning(f'Row count changed: {rows_in} -> {rows_out}')

    t4.to_csv(args.out_table4, index=False)
    log.info(f'Transformed TABLE4 written -> {args.out_table4}')

    # ------------------------------------------------------------------
    # Step 8 — Build RECONCILIATION output
    #
    # For each service category, aggregate bag-level charges per invoice
    # ID (including overflow columns) and compare to the TABLE1 category
    # charge for that invoice.
    # ------------------------------------------------------------------
    recon_rows = []

    for cfg in CATEGORY_CONFIG:
        if cfg['t1_charge'] is None:
            continue

        inv_col       = cfg['inv_id_col']
        chg_col       = cfg['charge_col']
        t1_chg        = cfg['t1_charge']
        label         = cfg['label']
        display_label = cfg.get('display_label', label)

        if inv_col not in t4.columns:
            continue

        n = max_ids.get(inv_col, 1)

        # All (inv_id_col, charge_col) pairs for this category (primary + overflow)
        col_pairs = [(inv_col, chg_col)]
        for i in range(2, n + 1):
            suffix  = f'_{i}'
            ov_inv  = inv_col + suffix
            ov_chg  = chg_col + suffix
            if ov_inv in t4.columns:
                col_pairs.append((ov_inv, ov_chg))

        # Aggregate total bag charge per invoice ID (vectorised groupby)
        agg = {}   # inv_id -> cumulative bag charge
        for ic, cc in col_pairs:
            if ic not in t4.columns or cc not in t4.columns:
                continue
            sub_id  = t4[ic].astype(str).str.strip().str.upper()
            sub_chg = pd.to_numeric(t4[cc], errors='coerce').fillna(0.0)
            valid   = sub_id.notna() & (sub_id != '') & (sub_id != 'NAN')
            grouped = sub_chg[valid].groupby(sub_id[valid])
            for inv_id, charge_sum in grouped.sum().items():
                agg[inv_id] = agg.get(inv_id, 0.0) + float(charge_sum)

        # Also include TABLE1 invoices that have a charge for this category
        # but zero bags allocated (they won't appear in agg at all).
        for t1_inv_id, inv_row in inv_lookup.items():
            if t1_inv_id not in agg:
                t1_val = safe_float(
                    inv_row[t1_chg] if t1_chg in inv_row.index else float('nan')
                )
                if t1_val != 0.0 and not math.isnan(t1_val):
                    agg[t1_inv_id] = 0.0

        for inv_id, bag_total in sorted(agg.items()):
            bag_total = round(bag_total, 6)

            if inv_id not in inv_lookup:
                log.warning(
                    f'[RECON] {label}: invoice {inv_id!r} present in TABLE4 '
                    f'but not found in TABLE1'
                )
                inv_amount  = None
                lsp_name    = ''
                vessel_name = ''
            else:
                inv_row     = inv_lookup[inv_id]
                inv_amount  = safe_float(
                    inv_row[t1_chg] if t1_chg in inv_row.index else float('nan')
                )
                inv_amount  = round(inv_amount, 6)
                lsp_name    = clean_str(inv_row.get('LSP NAME', ''))
                vessel_name = clean_str(inv_row.get('AOC VESSEL NAME', ''))

            if inv_amount is None:
                diff_val  = None
                match_str = '? (invoice not in TABLE1)'
            else:
                diff_val  = round(bag_total - inv_amount, 6)
                match_str = 'Match' if abs(diff_val) < 0.01 else 'Mismatch'

            recon_rows.append({
                'Invoice ID':                       inv_id,
                'Service Category':                 display_label,
                'LSP Name':                         lsp_name,
                'AOC Vessel Name':                  vessel_name,
                'Total Cost Allocated to Bags ($)': bag_total,
                'Total Invoice Amount ($)':         inv_amount if inv_amount is not None else '',
                'Difference ($)':                   diff_val   if diff_val   is not None else '',
                'Match?':                           match_str,
            })

    # Validation 2: flag any invoice/category pair where gap > $1.00
    inv_val_failures = 0
    for row in recon_rows:
        diff = row.get('Difference ($)')
        if diff != '' and diff is not None and abs(diff) > 1.00:
            inv_val_failures += 1
            log.warning(
                f'[VALIDATION-INV] {row["Service Category"]} | '
                f'Invoice {row["Invoice ID"]}: '
                f'bag total {row["Total Cost Allocated to Bags ($)"]:.2f} '
                f'vs invoice amount {row["Total Invoice Amount ($)"]:.2f} '
                f'(diff {diff:+.2f})'
            )

    recon_df = pd.DataFrame(recon_rows, columns=[
        'Invoice ID',
        'Service Category',
        'LSP Name',
        'AOC Vessel Name',
        'Total Cost Allocated to Bags ($)',
        'Total Invoice Amount ($)',
        'Difference ($)',
        'Match?',
    ])
    recon_df.to_csv(args.out_recon, index=False)
    log.info(f'Reconciliation written -> {args.out_recon}')

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    log.info('=' * 60)
    log.info('SUMMARY')
    log.info(f'  Rows processed               : {rows_in}')
    log.info(f'  Semicolon cells before       : {semicolon_before}')
    log.info(f'  Semicolon cells after        : {semicolon_after}')
    log.info(f'  Bag-level validation failures: {len(validation_bag_failures)}')
    log.info(f'  Invoice-level val. failures  : {inv_val_failures}')
    log.info(f'  Reconciliation rows          : {len(recon_rows)}')
    log.info('=' * 60)
    log.info('Done.')


if __name__ == '__main__':
    main()
