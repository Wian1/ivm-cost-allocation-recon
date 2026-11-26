"""Run folders, metadata, history and run-to-run comparison. UI-free."""
from __future__ import annotations

import json
import os
from datetime import datetime

import pandas as pd

from .reconcile import RECON_COLUMNS

RUNS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'runs')

FILES = {
    'table4_csv': 'table4_transformed.csv',
    'table4_parquet': 'table4_transformed.parquet',
    'recon_csv': 'reconciliation.csv',
    'recon_xlsx': 'reconciliation.xlsx',
    'log': 'transform.log',
    'warnings': 'transform_warnings.csv',
    'meta': 'run_metadata.json',
}


def new_run_dir(base: str = RUNS_DIR) -> str:
    os.makedirs(base, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    path = os.path.join(base, stamp)
    n = 1
    while os.path.exists(path):          # two runs in the same second
        n += 1
        path = os.path.join(base, f'{stamp}_{n}')
    os.makedirs(path)
    return path


def list_runs(base: str = RUNS_DIR) -> list[dict]:
    """Newest first. Runs without metadata (interrupted) are listed as incomplete."""
    if not os.path.isdir(base):
        return []
    out = []
    for name in sorted(os.listdir(base), reverse=True):
        d = os.path.join(base, name)
        if not os.path.isdir(d):
            continue
        mp = os.path.join(d, FILES['meta'])
        rec = {'name': name, 'path': d, 'complete': os.path.exists(mp)}
        if rec['complete']:
            try:
                with open(mp, encoding='utf-8') as f:
                    m = json.load(f)
                rec['meta'] = m
            except (OSError, json.JSONDecodeError):
                rec['complete'] = False
        out.append(rec)
    return out


def load_recon(run_path: str) -> pd.DataFrame:
    p = os.path.join(run_path, FILES['recon_csv'])
    return pd.read_csv(p, dtype={'Invoice ID': str}, keep_default_na=False, na_values=[''])


def compare_runs(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Compare two reconciliation frames (a = older, b = newer) on Invoice ID + category."""
    key = ['Invoice ID', 'Service Category']
    cols = key + ['Difference ($)', 'Match?', 'Total Cost Allocated to Bags ($)', 'Total Invoice Amount ($)']
    m = a[cols].merge(b[cols], on=key, how='outer', suffixes=(' (A)', ' (B)'), indicator=True)
    m['Difference ($) (A)'] = pd.to_numeric(m['Difference ($) (A)'], errors='coerce')
    m['Difference ($) (B)'] = pd.to_numeric(m['Difference ($) (B)'], errors='coerce')
    m['Change in difference ($)'] = (m['Difference ($) (B)'].fillna(0) - m['Difference ($) (A)'].fillna(0)).round(6)
    status = pd.Series('Unchanged', index=m.index)
    status[m['_merge'] == 'left_only'] = 'Only in run A'
    status[m['_merge'] == 'right_only'] = 'Only in run B'
    both = m['_merge'] == 'both'
    status[both & (m['Match? (A)'] != m['Match? (B)'])] = 'Match status changed'
    status[both & (m['Match? (A)'] == m['Match? (B)']) & (m['Change in difference ($)'].abs() > 1e-6)] = \
        'Difference changed'
    m['Change'] = status
    m = m.drop(columns=['_merge'])
    order = {'Match status changed': 0, 'Difference changed': 1, 'Only in run A': 2, 'Only in run B': 3,
             'Unchanged': 4}
    m = m.assign(_o=m['Change'].map(order), _a=m['Change in difference ($)'].abs())
    return m.sort_values(['_o', '_a'], ascending=[True, False]).drop(columns=['_o', '_a']).reset_index(drop=True)
