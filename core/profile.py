"""Quick profile of the two inputs (shown on the Upload page). UI-free."""
from __future__ import annotations

import pandas as pd

from .config import CATEGORY_CONFIG, T1_ID_COL, T4_WEIGHT_COLS
from .transform import build_lookup, parse_cells, prescan


def profile_inputs(t1_raw: pd.DataFrame, t4_raw: pd.DataFrame) -> dict:
    key = t1_raw[T1_ID_COL].fillna('').astype(str).str.strip().str.upper()
    valid = (key != '') & (key != 'NAN')
    dups = sorted(key[valid & key.duplicated(keep=False)].unique().tolist())

    max_ids, semi = prescan(t4_raw)
    rows, referenced = [], set()
    for cfg in CATEGORY_CONFIG:
        col = cfg['inv_id_col']
        if col in t4_raw.columns:
            s, v, _, _ = parse_cells(t4_raw[col])
            referenced |= set(s[v].str.upper().str.split(';').explode().str.strip().unique())
        rows.append({'Category': cfg.get('display_label', cfg['label']),
                     'Cells with several invoice IDs': semi[cfg['label']],
                     'Most IDs in one cell': max_ids[col],
                     'Extra column pairs to add': max_ids[col] - 1})
    referenced.discard('')

    missing_w = {}
    for c in T4_WEIGHT_COLS:
        if c in t4_raw.columns:
            missing_w[c] = int(pd.to_numeric(t4_raw[c], errors='coerce').isna().sum())
    return {
        't1_rows': len(t1_raw), 't4_rows': len(t4_raw),
        't1_unique_invoices': int(key[valid].nunique()),
        't4_referenced_invoices': len(referenced),
        'duplicate_t1_ids': dups,
        'categories': pd.DataFrame(rows),
        'missing_weights': missing_w,
        't4_columns': len(t4_raw.columns),
        'approx_memory_mb': round(t4_raw.head(20000).memory_usage(deep=True).sum() * len(t4_raw) / max(1, min(20000, len(t4_raw))) / 1e6),
    }
