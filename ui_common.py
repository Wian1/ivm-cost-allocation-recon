"""Shared helpers for the Streamlit pages."""
from __future__ import annotations

import json
import os

import pandas as pd
import streamlit as st

from core.config import DEFAULT_BAG_TOL, DEFAULT_INV_TOL, DEFAULT_MATCH_TOL
from core.loaders import check_schema, load_t1, load_t4
from core.profile import profile_inputs

ROOT = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(ROOT, 'uploads')
SETTINGS_FILE = os.path.join(ROOT, 'app_settings.json')

HELP = {
    'overflow': 'When a bag was covered by several invoices in one category, its extra invoice IDs are '
                'moved into additional ("extra") column pairs so that each charge sits against exactly one invoice.',
    'match_tol': 'An invoice counts as a Match when bag charges and invoice amount differ by no more than this.',
    'bag_tol': 'Flags a bag if its recalculated charges (summed over its invoices) differ from the '
               'charge it originally carried by more than this.',
    'inv_tol': 'Writes an invoice-level warning when allocated vs invoiced differs by more than this.',
}


def money(x, dec=2) -> str:
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return ''
    return f'${x:,.{dec}f}'


def default_input_dir() -> str:
    try:
        with open(SETTINGS_FILE, encoding='utf-8') as f:
            d = json.load(f).get('input_dir')
            if d and os.path.isdir(d):
                return d
    except (OSError, json.JSONDecodeError):
        pass
    for cand in ('inputs', 'references'):
        p = os.path.join(ROOT, cand)
        if os.path.isdir(p) and any(f.lower().endswith('.csv') for f in os.listdir(p)):
            return p
    return os.path.join(ROOT, 'inputs')


def save_input_dir(path: str):
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({'input_dir': path}, f)
    except OSError:
        pass


@st.cache_resource(show_spinner=False, max_entries=2)
def load_pair(t1_path: str, t1_sig: tuple, t4_path: str, t4_sig: tuple):
    """Read, schema-check and profile both files. Cached by path + size + mtime, so a
    second visit (or a re-run with other settings) does not re-read the 250 MB file."""
    t1 = load_t1(t1_path)
    t4 = load_t4(t4_path)
    return {'t1': t1, 't4': t4, 'schema': check_schema(t1.columns, t4.columns),
            'profile': profile_inputs(t1, t4)}


def file_sig(path: str) -> tuple:
    st_ = os.stat(path)
    return (st_.st_size, int(st_.st_mtime))


def require_inputs():
    if 'loaded' not in st.session_state:
        st.info('Start on the **1. Upload & check** page and load the two files first.')
        st.stop()
    return st.session_state['loaded']


def require_result():
    if 'result' not in st.session_state:
        st.info('No results yet. Load the files and click **Run** on the **2. Run** page.')
        st.stop()
    return st.session_state['result']


def style_recon(df: pd.DataFrame):
    """Colour-code Mismatch (red) and invoice-not-in-TABLE-1 (amber)."""
    def row_style(r):
        m = str(r.get('Match?', ''))
        if m == 'Mismatch':
            return ['background-color: rgba(220,53,69,0.16)'] * len(r)
        if m.startswith('?'):
            return ['background-color: rgba(255,193,7,0.20)'] * len(r)
        return [''] * len(r)
    if df.size > 250_000:
        return df
    fmt = {c: '{:,.2f}' for c in df.columns if c.endswith('($)') and pd.api.types.is_numeric_dtype(df[c])}
    return df.style.apply(row_style, axis=1).format(fmt, na_rep='')
