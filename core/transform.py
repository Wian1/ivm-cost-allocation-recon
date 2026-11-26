"""Split semicolon invoice IDs into overflow columns and recalculate charges. UI-free.

This is a vectorised re-implementation of references/transform_table4.py. The numbers
must stay identical to that script (see tests/test_regression.py). Behaviours that look
odd but are deliberate parts of the original logic:

  * If the FIRST id of a semicolon cell is not in TABLE 1, the primary cell is left as
    the raw text (semicolons included) and the "semicolons after" count reports it.
  * Overflow columns are indexed by the id's position in the cell, so a skipped
    (unknown) id leaves its overflow slot empty.
  * Duplicate ids inside one cell are each processed, and each counts towards the
    invoice's tonnage sum / bag count.
  * Per-invoice tonnage / bag-count denominators use ALL bags that reference the invoice
    (single-id and semicolon cells), taken from the TABLE 4 data before any changes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .config import (
    CATEGORY_CONFIG, DEFAULT_BAG_TOL, DEFAULT_INV_TOL, DEFAULT_MATCH_TOL, T1_ID_COL, T4_BAG_COL,
)
from .runlog import RunLog

Progress = Callable[[int, str, float | None], None]


@dataclass
class Settings:
    full_recalc: bool = False
    bag_tol: float = DEFAULT_BAG_TOL
    inv_tol: float = DEFAULT_INV_TOL
    match_tol: float = DEFAULT_MATCH_TOL

    def to_dict(self) -> dict:
        return {'full_recalc': self.full_recalc, 'bag_tol': self.bag_tol,
                'inv_tol': self.inv_tol, 'match_tol': self.match_tol}


@dataclass
class TransformResult:
    t4: pd.DataFrame
    max_ids: dict
    semicolon_before: int
    semicolon_after: int
    rows_in: int
    rows_out: int
    bag_failures: pd.DataFrame
    lookup: pd.DataFrame
    semicolon_cells_by_category: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# ID parsing helpers (vectorised equivalents of clean_id / split_ids)
# ---------------------------------------------------------------------------
def _noop_progress(step, label, frac=None):
    pass


def parse_cells(col: pd.Series):
    """Return (stripped text, valid, semicolon, single) for an invoice-ID column."""
    s = col.fillna('').astype(str).str.strip()
    valid = (s != '') & (s.str.lower() != 'nan')
    semi = valid & s.str.contains(';', regex=False)
    return s, valid, semi, valid & ~semi


def _explode_semi(s: pd.Series, semi: pd.Series) -> pd.DataFrame:
    """One row per cleaned id of every semicolon cell: columns row, pos, id."""
    semi_pos = np.flatnonzero(semi.to_numpy())
    if len(semi_pos) == 0:
        return pd.DataFrame({'row': np.array([], dtype=int), 'pos': np.array([], dtype=int),
                             'id': np.array([], dtype=object)})
    ex = pd.Series(s.to_numpy()[semi_pos]).str.split(';').explode()
    e = ex.str.strip()
    keep = ((e != '') & (e.str.lower() != 'nan')).to_numpy()
    rows = semi_pos[ex.index.to_numpy()][keep]
    ids = e.to_numpy()[keep]
    ids = pd.Series(ids, dtype=object).str.upper().to_numpy()
    pos = pd.Series(rows).groupby(rows).cumcount().to_numpy()
    return pd.DataFrame({'row': rows, 'pos': pos, 'id': ids})


def explode_ids(s, semi, single) -> pd.DataFrame:
    """All (row, pos, id) occurrences for one invoice-ID column, plus an is_semi flag."""
    sp = np.flatnonzero(single.to_numpy())
    single_df = pd.DataFrame({
        'row': sp, 'pos': np.zeros(len(sp), dtype=int),
        'id': pd.Series(s.to_numpy()[sp], dtype=object).str.upper().to_numpy()})
    single_df['is_semi'] = False
    semi_df = _explode_semi(s, semi)
    semi_df['is_semi'] = True
    return pd.concat([single_df, semi_df], ignore_index=True)


def prescan(t4: pd.DataFrame) -> tuple[dict, dict]:
    """Max ids in one cell per invoice-ID column, and semicolon cell counts per category."""
    max_ids, semi_counts = {}, {}
    for cfg in CATEGORY_CONFIG:
        inv_col = cfg['inv_id_col']
        if inv_col not in t4.columns:
            max_ids[inv_col] = 1
            semi_counts[cfg['label']] = 0
            continue
        s, _, semi, _ = parse_cells(t4[inv_col])
        semi_counts[cfg['label']] = int(s.str.contains(';', regex=False).sum())
        d = _explode_semi(s, semi)
        max_ids[inv_col] = max(1, int(d['pos'].max()) + 1) if len(d) else 1
    return max_ids, semi_counts


def build_lookup(t1: pd.DataFrame, log: RunLog | None = None) -> pd.DataFrame:
    """TABLE 1 indexed by upper-cased invoice id; duplicates: last row wins."""
    key = t1[T1_ID_COL].fillna('').astype(str).str.strip().str.upper()
    valid = (key != '') & (key != 'NAN')
    dup = key.duplicated(keep=False) & valid
    if log is not None and dup.any():
        log.warn('duplicate_invoice_t1',
                 f'Duplicate INVOICE ID. values in TABLE1 (last row used): '
                 f'{sorted(key[dup].unique().tolist())}')
    lk = t1.loc[valid].copy()
    lk['_inv_key'] = key[valid]
    lk = lk.drop_duplicates('_inv_key', keep='last').set_index('_inv_key')
    return lk


def _amount_series(lookup: pd.DataFrame, t1_col: str) -> pd.Series:
    if t1_col in lookup.columns:
        return pd.to_numeric(lookup[t1_col], errors='coerce').fillna(0.0)
    return pd.Series(0.0, index=lookup.index)


def _clean_str_series(s: pd.Series) -> pd.Series:
    s = s.fillna('').astype(str).str.strip()
    return s.where(s.str.lower() != 'nan', '')


# ---------------------------------------------------------------------------
# Main transform (steps 2-6 of the original script)
# ---------------------------------------------------------------------------
def transform_table4(t1: pd.DataFrame, t4: pd.DataFrame, settings: Settings,
                     log: RunLog, progress: Progress = _noop_progress) -> TransformResult:
    """t1 / t4 must already be numeric-converted (loaders.convert_t1 / convert_t4).
    The input frames are not modified."""
    rows_in = len(t4)
    n_rows = rows_in

    # Step 2 -------------------------------------------------------------
    progress(2, 'Building invoice lookup', None)
    lookup = build_lookup(t1, log)
    log.info(f'TABLE1 lookup built: {len(lookup)} unique invoice IDs')

    # Step 3 -------------------------------------------------------------
    progress(3, 'Scanning for multi-invoice cells', None)
    max_ids, semi_counts = prescan(t4)
    for cfg in CATEGORY_CONFIG:
        m = max_ids[cfg['inv_id_col']]
        if m > 1:
            log.info(f'Category {cfg["label"]!r}: max {m} IDs in one cell '
                     f'({m - 1} overflow column(s) will be added)')
    semicolon_before = 0
    for cfg in CATEGORY_CONFIG:
        if cfg['inv_id_col'] in t4.columns:
            semicolon_before += semi_counts[cfg['label']]
    log.info(f'Semicolon cells BEFORE transformation: {semicolon_before}')

    # Step 4 -------------------------------------------------------------
    progress(4, 'Planning extra columns', None)
    original_columns = list(t4.columns)
    overflow_chg, overflow_inv = {}, {}
    for cfg in CATEGORY_CONFIG:
        n = max_ids.get(cfg['inv_id_col'], 1)
        overflow_inv[cfg['inv_id_col']] = [f"{cfg['inv_id_col']}_{i}" for i in range(2, n + 1)]
        overflow_chg[cfg['charge_col']] = [f"{cfg['charge_col']}_{i}" for i in range(2, n + 1)]
    ordered_cols = []
    for col in original_columns:
        ordered_cols.append(col)
        ordered_cols.extend(overflow_chg.get(col, []))
        ordered_cols.extend(overflow_inv.get(col, []))
    # (overflow names never collide with existing columns; a collision would duplicate a name)
    seen = set()
    ordered_cols = [c for c in ordered_cols if not (c in seen or seen.add(c))]

    # Step 5 -------------------------------------------------------------
    out: dict[str, pd.Series] = {}          # replaced / new columns
    bag_series = (_clean_str_series(t4[T4_BAG_COL]) if T4_BAG_COL in t4.columns
                  else pd.Series(t4.index.astype(str), index=t4.index))
    bag_arr = bag_series.to_numpy()
    failures = []
    n_cat = len(CATEGORY_CONFIG)

    for ci, cfg in enumerate(CATEGORY_CONFIG):
        inv_col, chg_col = cfg['inv_id_col'], cfg['charge_col']
        t4_ton, label = cfg['t4_tonnage'], cfg['label']
        per_bag = cfg.get('recalc_method') == 'per_bag'
        progress(5, f'Recalculating: {label}', ci / n_cat)

        if inv_col not in t4.columns:
            log.warn('column_skipped',
                     f'[{label}] Invoice ID column {inv_col!r} not in TABLE4 - skipping',
                     category=label)
            continue

        s, valid, semi, single = parse_cells(t4[inv_col])
        L = explode_ids(s, semi, single)
        semi_cells = int(semi.sum())
        if semi_cells:
            log.info(f'[{label}] Processing {semi_cells} semicolon row(s)')

        amount_map = _amount_series(lookup, cfg['t1_charge'])
        L['found'] = L['id'].isin(lookup.index)
        L['amt'] = L['id'].map(amount_map).fillna(0.0)

        if per_bag:
            counts = L.groupby('id').size()
            L['charge'] = (L['amt'] / L['id'].map(counts)).round(6)
            L['tonsum'] = np.nan
        else:
            if t4_ton in t4.columns:
                ton = pd.to_numeric(t4[t4_ton], errors='coerce').fillna(0.0).to_numpy()
            else:
                ton = np.zeros(n_rows)
            L['bag_ton'] = ton[L['row'].to_numpy()]
            tonsum = L.groupby('id')['bag_ton'].sum() if t4_ton in t4.columns else \
                pd.Series(0.0, index=L['id'].unique())
            L['tonsum'] = L['id'].map(tonsum)
            with np.errstate(divide='ignore', invalid='ignore'):
                rate = L['amt'] / L['tonsum']
            L['charge'] = np.where(L['tonsum'] == 0, 0.0, rate * L['bag_ton']).round(6)

        # -- new primary invoice-id column: single rows upper-cased --------
        res_inv = t4[inv_col].astype(object).copy()
        res_inv.iloc[np.flatnonzero(single.to_numpy())] = s[single].str.upper().to_numpy()
        res_chg = t4[chg_col].copy() if chg_col in t4.columns else None
        ov_inv = {k: pd.Series('', index=t4.index, dtype=object)
                  for k in range(2, max_ids[inv_col] + 1)}
        ov_chg = {k: pd.Series(np.nan, index=t4.index, dtype='float64')
                  for k in range(2, max_ids[inv_col] + 1)}

        Ls = L[L['is_semi']]
        # warnings: unknown invoice id (semicolon rows only, as original)
        nf = Ls[~Ls['found']]
        if len(nf):
            log.warn_many([
                dict(kind='invoice_not_in_t1',
                     msg=f'[{label}] BAG {bag_arr[r]}: invoice {i!r} not found in TABLE1 - skipping this ID',
                     category=label, invoice_id=i, bag_id=bag_arr[r])
                for r, i in zip(nf['row'].to_numpy(), nf['id'].to_numpy())])
        # warnings: zero tonnage
        if not per_bag:
            zt = Ls[Ls['found'] & (Ls['tonsum'] == 0)]
            if len(zt):
                log.warn_many([
                    dict(kind='zero_tonnage',
                         msg=f'[{label}] Invoice {i}: zero T4 tonnage sum (col {t4_ton!r}) - charge forced to 0.0',
                         category=label, invoice_id=i, bag_id=bag_arr[r],
                         amount=float(a))
                    for r, i, a in zip(zt['row'].to_numpy(), zt['id'].to_numpy(), zt['amt'].to_numpy())])

        Lf = Ls[Ls['found']]
        # write recalculated ids / charges
        p0 = Lf[Lf['pos'] == 0]
        if len(p0):
            res_inv.iloc[p0['row'].to_numpy()] = p0['id'].to_numpy()
            if res_chg is not None:
                res_chg.iloc[p0['row'].to_numpy()] = p0['charge'].to_numpy()
        for k in range(2, max_ids[inv_col] + 1):
            pk = Lf[Lf['pos'] == k - 1]
            if len(pk):
                ov_inv[k].iloc[pk['row'].to_numpy()] = pk['id'].to_numpy()
                ov_chg[k].iloc[pk['row'].to_numpy()] = pk['charge'].to_numpy()

        # validation 1: recalculated sum vs original charge, per semicolon row
        if len(Ls):
            rec = Lf.groupby('row')['charge'].sum().reindex(Ls['row'].unique()).fillna(0.0)
            if chg_col in t4.columns:
                orig = t4[chg_col].fillna(0.0).to_numpy()[rec.index.to_numpy()]
            else:
                orig = np.zeros(len(rec))
            diff = np.abs(rec.to_numpy() - orig)
            bad = diff > settings.bag_tol
            for r, rc, og, d in zip(rec.index.to_numpy()[bad], rec.to_numpy()[bad],
                                    orig[bad], diff[bad]):
                msg = (f'[VALIDATION-BAG] [{label}] BAG {bag_arr[r]}: recalc sum {rc:.6f} '
                       f'vs original {og:.6f} (diff {d:.6f})')
                log.warn('validation_bag', msg, category=label, bag_id=bag_arr[r], amount=float(d))
                failures.append({'Category': cfg['display_label'], 'Bag ID': bag_arr[r],
                                 'Recalculated Sum ($)': float(rc), 'Original Charge ($)': float(og),
                                 'Difference ($)': float(rc - og)})

        # full recalc of single-id rows
        if settings.full_recalc and res_chg is not None:
            Lsg = L[(~L['is_semi']) & L['found']]
            if len(Lsg):
                log.info(f'[{label}] --full-recalc: recalculating {int((~L["is_semi"]).sum())} single-invoice row(s)')
                res_chg.iloc[Lsg['row'].to_numpy()] = Lsg['charge'].to_numpy()

        out[inv_col] = res_inv
        if res_chg is not None:
            out[chg_col] = res_chg
        for k in ov_inv:
            out[f'{inv_col}_{k}'] = ov_inv[k]
            out[f'{chg_col}_{k}'] = ov_chg[k]
        del L, Ls, Lf

    # Overflow columns for categories that were skipped still need to exist
    for col in ordered_cols:
        if col not in out and col not in t4.columns:
            out[col] = pd.Series(np.nan, index=t4.index)

    progress(5, 'Assembling transformed table', 1.0)
    t4_out = pd.concat([(out[c] if c in out else t4[c]).rename(c) for c in ordered_cols], axis=1)

    # Step 6 -------------------------------------------------------------
    progress(6, 'Checking no semicolons remain', None)
    semicolon_after = 0
    for cfg in CATEGORY_CONFIG:
        inv_col = cfg['inv_id_col']
        for c in [inv_col] + overflow_inv[inv_col]:
            if c in t4_out.columns:
                semicolon_after += int(t4_out[c].fillna('').astype(str).str.contains(';', regex=False).sum())
    log.info(f'Semicolon cells AFTER transformation: {semicolon_after}')
    if semicolon_after > 0:
        log.warn('semicolon_remaining',
                 'Non-zero semicolon cells remain after transformation - investigate!')

    rows_out = len(t4_out)
    log.info(f'Rows in: {rows_in}  |  Rows out: {rows_out}')
    if rows_in != rows_out:
        log.warn('row_count', f'Row count changed: {rows_in} -> {rows_out}')

    bag_failures = pd.DataFrame(failures, columns=[
        'Category', 'Bag ID', 'Recalculated Sum ($)', 'Original Charge ($)', 'Difference ($)'])
    return TransformResult(t4_out, max_ids, semicolon_before, semicolon_after, rows_in, rows_out,
                           bag_failures, lookup, semi_counts)
