"""Reconciliation of bag-allocated totals vs invoice totals, and issue classification. UI-free."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .config import CATEGORY_CONFIG, EXACT_TOL, T1_LSP_COL, T1_VESSEL_COL
from .runlog import RunLog
from .transform import Settings, _amount_series, _clean_str_series

RECON_COLUMNS = [
    'Invoice ID', 'Service Category', 'LSP Name', 'AOC Vessel Name',
    'Total Cost Allocated to Bags ($)', 'Total Invoice Amount ($)', 'Difference ($)', 'Match?',
]
EXTRA_COLUMNS = ['Bags Referencing Invoice']   # extra info used by the app (not in original CSV)
NOT_IN_T1 = '? (invoice not in TABLE1)'


def reconcile(t4: pd.DataFrame, lookup: pd.DataFrame, max_ids: dict,
              settings: Settings, log: RunLog) -> pd.DataFrame:
    frames = []
    lsp = _clean_str_series(lookup[T1_LSP_COL]) if T1_LSP_COL in lookup.columns else \
        pd.Series('', index=lookup.index)
    ves = _clean_str_series(lookup[T1_VESSEL_COL]) if T1_VESSEL_COL in lookup.columns else \
        pd.Series('', index=lookup.index)

    for cfg in CATEGORY_CONFIG:
        inv_col, chg_col = cfg['inv_id_col'], cfg['charge_col']
        label, display = cfg['label'], cfg.get('display_label', cfg['label'])
        if inv_col not in t4.columns:
            continue
        n = max_ids.get(inv_col, 1)
        pairs = [(inv_col, chg_col)] + [
            (f'{inv_col}_{i}', f'{chg_col}_{i}') for i in range(2, n + 1)
            if f'{inv_col}_{i}' in t4.columns]

        sums, cnts = [], []
        for ic, cc in pairs:
            if ic not in t4.columns or cc not in t4.columns:
                continue
            sid = t4[ic].fillna('').astype(str).str.strip().str.upper()
            chg = pd.to_numeric(t4[cc], errors='coerce').fillna(0.0)
            ok = (sid != '') & (sid != 'NAN')
            sums.append(chg[ok].groupby(sid[ok]).sum())
            cnts.append(sid[ok].groupby(sid[ok]).size())
        agg = pd.concat(sums).groupby(level=0).sum() if sums else pd.Series(dtype=float)
        cnt = pd.concat(cnts).groupby(level=0).sum() if cnts else pd.Series(dtype=int)

        amount = _amount_series(lookup, cfg['t1_charge'])
        # invoices with an amount but no bags
        extra = amount.index[(amount != 0.0) & ~amount.index.isin(agg.index)]
        ids = sorted(set(agg.index) | set(extra))
        if not ids:
            continue
        df = pd.DataFrame({'Invoice ID': ids})
        df['Service Category'] = display
        in_t1 = df['Invoice ID'].isin(lookup.index)
        df['LSP Name'] = df['Invoice ID'].map(lsp).where(in_t1, '').fillna('')
        df['AOC Vessel Name'] = df['Invoice ID'].map(ves).where(in_t1, '').fillna('')
        bag_total = df['Invoice ID'].map(agg).fillna(0.0).round(6)
        inv_amt = df['Invoice ID'].map(amount).round(6).where(in_t1)
        diff = (bag_total - inv_amt).round(6)
        df['Total Cost Allocated to Bags ($)'] = bag_total
        df['Total Invoice Amount ($)'] = inv_amt
        df['Difference ($)'] = diff
        df['Match?'] = np.where(~in_t1, NOT_IN_T1,
                                np.where(diff.abs() <= settings.match_tol, 'Match', 'Mismatch'))
        df['Bags Referencing Invoice'] = df['Invoice ID'].map(cnt).fillna(0).astype(int)
        frames.append(df)

        for inv_id in df.loc[~in_t1, 'Invoice ID']:
            log.warn('recon_not_in_t1',
                     f'[RECON] {label}: invoice {inv_id!r} present in TABLE4 but not found in TABLE1',
                     category=display, invoice_id=inv_id)

    recon = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=RECON_COLUMNS + EXTRA_COLUMNS)

    big = recon[recon['Difference ($)'].abs() > settings.inv_tol]
    for _, r in big.iterrows():
        d = r['Difference ($)']
        log.warn('validation_inv',
                 f'[VALIDATION-INV] {r["Service Category"]} | Invoice {r["Invoice ID"]}: '
                 f'bag total {r["Total Cost Allocated to Bags ($)"]:.2f} vs invoice amount '
                 f'{r["Total Invoice Amount ($)"]:.2f} (diff {d:+.2f})',
                 category=r['Service Category'], invoice_id=r['Invoice ID'], amount=float(d))
    return recon[RECON_COLUMNS + EXTRA_COLUMNS]


# ---------------------------------------------------------------------------
# Issues panel
# ---------------------------------------------------------------------------
ISSUE_ORDER = ['no_bags', 'not_in_t1', 'rounding', 'material', 'zero_tonnage', 'bag_validation']


def classify_issues(recon: pd.DataFrame, warnings: pd.DataFrame, bag_failures: pd.DataFrame,
                    settings: Settings) -> dict:
    """Return {key: {title, help, count, impact, impact_label, df, extra}} for the issues panel."""
    diff = recon['Difference ($)']
    amt = recon['Total Invoice Amount ($)']
    bags = recon['Bags Referencing Invoice']
    not_in_t1 = recon['Match?'] == NOT_IN_T1
    in_t1 = ~not_in_t1

    no_bags = recon[in_t1 & (bags == 0) & (amt != 0)].copy()
    no_bags['Credit / negative amount'] = no_bags['Total Invoice Amount ($)'] < 0

    nt = recon[not_in_t1]
    rounding = recon[in_t1 & (diff.abs() > EXACT_TOL) & (diff.abs() <= settings.match_tol)]
    material = recon[in_t1 & (bags > 0) & (diff.abs() > settings.match_tol)]

    zt = warnings[warnings['kind'] == 'zero_tonnage'] if len(warnings) else warnings
    if len(zt):
        zt = (zt.groupby(['category', 'invoice_id'], as_index=False)
                .agg(**{'Bags affected': ('bag_id', 'size'), 'Invoice Amount ($)': ('amount', 'first')})
                .rename(columns={'category': 'Service Category', 'invoice_id': 'Invoice ID'}))
    else:
        zt = pd.DataFrame(columns=['Service Category', 'Invoice ID', 'Bags affected', 'Invoice Amount ($)'])

    n_credit = int(no_bags['Credit / negative amount'].sum())
    gross = float(no_bags['Total Invoice Amount ($)'].abs().sum())
    net = float(no_bags['Total Invoice Amount ($)'].sum())

    return {
        'no_bags': dict(
            title='Invoice with no bags allocated',
            help=('The invoice has an amount in TABLE 1 but no bag in TABLE 4 references it, so nothing '
                  'was allocated. Check TABLE 4. Negative amounts are credit notes / reversals and may '
                  'be expected to have no bags.'),
            count=len(no_bags), impact=net, impact_label='Net invoice value not allocated ($)',
            df=no_bags,
            extra={'credit_count': n_credit, 'gross': gross, 'net': net,
                   'credit_total': float(no_bags.loc[no_bags['Credit / negative amount'],
                                                     'Total Invoice Amount ($)'].sum())}),
        'not_in_t1': dict(
            title='Invoice not in TABLE 1',
            help='Bags reference this invoice but TABLE 1 has no such invoice. Those bag charges '
                 'cannot be checked.',
            count=len(nt), impact=float(nt['Total Cost Allocated to Bags ($)'].sum()),
            impact_label='Bag charges against unknown invoices ($)', df=nt, extra={}),
        'rounding': dict(
            title='Matched within tolerance, not exact',
            help=f'Difference is more than ${EXACT_TOL:.2f} but within the ${settings.match_tol:.2f} '
                 f'match tolerance, so these count as Match. Informational only.',
            count=len(rounding), impact=float(rounding['Difference ($)'].abs().sum()),
            impact_label='Sum of absolute differences ($)', df=rounding, extra={}),
        'material': dict(
            title='Material difference',
            help=f'Bags reference the invoice, but the allocated total differs from the invoice by more '
                 f'than ${settings.match_tol:.2f}. Often caused by bags that carry the invoice in a '
                 f'different column, or by per-bag demurrage splits.',
            count=len(material), impact=float(material['Difference ($)'].abs().sum()),
            impact_label='Sum of absolute differences ($)', df=material, extra={}),
        'zero_tonnage': dict(
            title='Zero-tonnage invoice',
            help='Bags on this invoice have no tonnage in TABLE 4, so the charge was forced to $0.',
            count=len(zt), impact=float(zt['Invoice Amount ($)'].sum()) if len(zt) else 0.0,
            impact_label='Invoice value forced to $0 ($)', df=zt, extra={}),
        'bag_validation': dict(
            title='Bag-level check failures',
            help=f'For bags that had several invoice IDs, the recalculated charges do not add up to the '
                 f'bag\'s original charge (tolerance ${settings.bag_tol:.2f}).',
            count=len(bag_failures),
            impact=float(bag_failures['Difference ($)'].abs().sum()) if len(bag_failures) else 0.0,
            impact_label='Sum of absolute differences ($)', df=bag_failures, extra={}),
    }
