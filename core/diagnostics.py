"""Invoice drill-down and sub-invoice diagnostic. UI-free."""
from __future__ import annotations

import pandas as pd

from .config import CATEGORY_CONFIG, T4_BAG_COL


def category_by_display(display_label: str) -> dict:
    return next(c for c in CATEGORY_CONFIG if c.get('display_label', c['label']) == display_label)


def _pairs(t4_out: pd.DataFrame, cfg: dict, max_ids: dict):
    inv, chg = cfg['inv_id_col'], cfg['charge_col']
    n = max_ids.get(inv, 1)
    return [(inv, chg)] + [(f'{inv}_{i}', f'{chg}_{i}') for i in range(2, n + 1)
                           if f'{inv}_{i}' in t4_out.columns]


def invoice_drilldown(t4_in: pd.DataFrame, t4_out: pd.DataFrame, max_ids: dict,
                      display_label: str, invoice_id: str) -> pd.DataFrame:
    """Bags that reference an invoice for a category: tonnage, original vs recalculated charge,
    and the other invoices on the same bag (same category)."""
    cfg = category_by_display(display_label)
    pairs = _pairs(t4_out, cfg, max_ids)
    inv_id = str(invoice_id).strip().upper()

    ids = {ic: t4_out[ic].fillna('').astype(str).str.strip().str.upper() for ic, _ in pairs}
    mask = pd.Series(False, index=t4_out.index)
    for ic, _ in pairs:
        mask |= ids[ic] == inv_id
    rows = t4_out.index[mask]

    recalced = pd.Series(0.0, index=rows)
    others = pd.Series([[] for _ in rows], index=rows, dtype=object)
    for ic, cc in pairs:
        hit = ids[ic].loc[rows] == inv_id
        chg = pd.to_numeric(t4_out.loc[rows, cc], errors='coerce').fillna(0.0)
        recalced += chg.where(hit, 0.0)
        for r in rows[(~hit) & (ids[ic].loc[rows] != '')]:
            others[r] = others[r] + [ids[ic].loc[r]]

    out = pd.DataFrame(index=rows)
    out['Bag ID'] = t4_out.loc[rows, T4_BAG_COL] if T4_BAG_COL in t4_out.columns else rows.astype(str)
    ton = cfg['t4_tonnage']
    out['Tonnage (tons)'] = t4_out.loc[rows, ton] if ton in t4_out.columns else float('nan')
    out['Tonnage basis'] = ton
    out['Invoice IDs in original cell'] = t4_in.loc[rows, cfg['inv_id_col']].fillna('') \
        if cfg['inv_id_col'] in t4_in.columns else ''
    out['Original charge on bag ($)'] = pd.to_numeric(t4_in.loc[rows, cfg['charge_col']], errors='coerce') \
        if cfg['charge_col'] in t4_in.columns else float('nan')
    out['Recalculated charge for this invoice ($)'] = recalced.round(6)
    out['Other invoices on this bag'] = others.map(lambda x: '; '.join(x))
    return out.reset_index(drop=True)


def subinvoice_diagnostic(recon: pd.DataFrame, t4_out: pd.DataFrame, max_ids: dict) -> pd.DataFrame:
    """For zero-bag invoices whose ID contains '/', check the TABLE 4 data directly:
    is that exact ID used in ANY category, and are sibling sub-invoices (same base) used?"""
    z = recon[(recon['Bags Referencing Invoice'] == 0) & (recon['Match?'] != '? (invoice not in TABLE1)')
              & recon['Invoice ID'].str.contains('/', regex=False)].copy()
    if z.empty:
        return pd.DataFrame(columns=['Invoice ID', 'Service Category', 'Total Invoice Amount ($)',
                                     'Exact ID found in TABLE 4 (any category)',
                                     'Sibling sub-invoices found in TABLE 4'])
    used = set()
    for cfg in CATEGORY_CONFIG:
        for ic, _ in _pairs(t4_out, cfg, max_ids):
            if ic in t4_out.columns:
                used |= set(t4_out[ic].dropna().astype(str).str.strip().str.upper().unique())
    used.discard('')
    by_base: dict[str, list[str]] = {}
    for u in used:
        if '/' in u:
            by_base.setdefault(u.split('/')[0], []).append(u)
    z['Exact ID found in TABLE 4 (any category)'] = z['Invoice ID'].isin(used)
    z['Sibling sub-invoices found in TABLE 4'] = z['Invoice ID'].map(
        lambda i: ', '.join(sorted(by_base.get(i.split('/')[0], []))))
    return z[['Invoice ID', 'Service Category', 'Total Invoice Amount ($)',
              'Exact ID found in TABLE 4 (any category)', 'Sibling sub-invoices found in TABLE 4']]
