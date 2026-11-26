"""Regression: the new core module must reproduce the ORIGINAL script's output.

Golden files were produced by running references/transform_table4.py on the same inputs
(tests/make_samples.py). Numbers must agree within 1e-6.

The ONE deliberate difference is the 'Match?' column: the original used |diff| < 0.01, the
app uses |diff| <= 1.00 (user-requested change), so Match? is checked against the golden
Difference using the new rule, and the original rule is checked for consistency too.
"""
import os
import numpy as np
import pandas as pd
import pytest

from core.config import CATEGORY_CONFIG, T4_WEIGHT_COLS
from core.loaders import load_t1, load_t4
from core.pipeline import run_frames
from core.reconcile import NOT_IN_T1, RECON_COLUMNS
from core.transform import Settings

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, 'tests', 'data')
TOL = 1e-6

CHARGE_COLS = {c['charge_col'] for c in CATEGORY_CONFIG}


def _is_numeric_col(name: str) -> bool:
    base = name.rsplit('_', 1)[0] if name.rsplit('_', 1)[-1].isdigit() else name
    return base in CHARGE_COLS or name in T4_WEIGHT_COLS


def compare_table4(mine: pd.DataFrame, golden: pd.DataFrame):
    assert list(mine.columns) == list(golden.columns), 'column names / order differ'
    assert len(mine) == len(golden)
    bad = []
    for c in mine.columns:
        if _is_numeric_col(c):
            a = pd.to_numeric(mine[c], errors='coerce').to_numpy(dtype=float)
            b = pd.to_numeric(golden[c], errors='coerce').to_numpy(dtype=float)
            same = (np.isnan(a) & np.isnan(b)) | (np.abs(np.nan_to_num(a) - np.nan_to_num(b)) <= TOL)
            if not same.all():
                bad.append((c, int((~same).sum())))
        else:
            a = mine[c].fillna('').astype(str).to_numpy()
            b = golden[c].fillna('').astype(str).to_numpy()
            if not (a == b).all():
                bad.append((c, int((a != b).sum())))
    assert not bad, f'columns with differences: {bad[:10]}'


def compare_recon(mine: pd.DataFrame, golden: pd.DataFrame, match_tol=1.0):
    m = mine[RECON_COLUMNS].reset_index(drop=True)
    g = golden[RECON_COLUMNS].reset_index(drop=True)
    assert len(m) == len(g)
    for c in ['Invoice ID', 'Service Category', 'LSP Name', 'AOC Vessel Name']:
        assert (m[c].fillna('').astype(str) == g[c].fillna('').astype(str)).all(), c
    for c in ['Total Cost Allocated to Bags ($)', 'Total Invoice Amount ($)', 'Difference ($)']:
        a = pd.to_numeric(m[c], errors='coerce').to_numpy(dtype=float)
        b = pd.to_numeric(g[c], errors='coerce').to_numpy(dtype=float)
        assert ((np.isnan(a) & np.isnan(b)) | (np.abs(np.nan_to_num(a) - np.nan_to_num(b)) <= TOL)).all(), c
    # Match? : new rule applied to the golden difference
    d = pd.to_numeric(g['Difference ($)'], errors='coerce')
    expected = np.where(d.isna(), NOT_IN_T1, np.where(d.abs() <= match_tol, 'Match', 'Mismatch'))
    assert (m['Match?'].to_numpy() == expected).all()
    # and the original rule is consistent with the golden file itself
    orig = np.where(d.isna(), NOT_IN_T1, np.where(d.abs() < 0.01, 'Match', 'Mismatch'))
    assert (g['Match?'].to_numpy() == orig).all()


@pytest.fixture(scope='module')
def inputs():
    return (load_t1(os.path.join(DATA, 'table1.csv')),
            load_t4(os.path.join(DATA, 'table4_sample.csv')))


@pytest.mark.parametrize('mode,folder', [(False, 'golden_default'), (True, 'golden_fullrecalc')])
def test_sample_matches_original(inputs, mode, folder):
    t1, t4 = inputs
    res = run_frames(t1, t4, Settings(full_recalc=mode))
    gold_t4 = pd.read_csv(os.path.join(DATA, folder, 'table4_transformed.csv'), dtype=str)
    gold_rc = pd.read_csv(os.path.join(DATA, folder, 'reconciliation.csv'), dtype=str)
    compare_table4(res.transform.t4, gold_t4)
    compare_recon(res.recon, gold_rc)
    assert res.transform.semicolon_after == 0
    assert res.transform.rows_in == res.transform.rows_out == len(t4)
    log = open(os.path.join(DATA, folder, 'transform.log'), encoding='utf-8').read()
    assert f'Semicolon cells before       : {res.transform.semicolon_before}' in log
    assert f'Bag-level validation failures: {len(res.transform.bag_failures)}' in log


def test_inputs_not_mutated(inputs):
    t1, t4 = inputs
    before = t4.copy()
    run_frames(t1, t4, Settings())
    pd.testing.assert_frame_equal(t4, before)


@pytest.mark.full
def test_full_files_match_original():
    ref = os.path.join(ROOT, 'references')
    gold = os.path.join(ROOT, 'golden', 'full')
    t1 = load_t1(os.path.join(ref, 'INVOICE - COST ALLOCATION - TABLE 1.csv'))
    t4 = load_t4(os.path.join(ref, 'BAG - COST ALLOCATION - TABLE 4.csv'))
    res = run_frames(t1, t4, Settings())
    compare_table4(res.transform.t4, pd.read_csv(os.path.join(gold, 'table4_transformed.csv'), dtype=str))
    compare_recon(res.recon, pd.read_csv(os.path.join(gold, 'reconciliation.csv'), dtype=str))
    assert res.transform.semicolon_before == 157274 and res.transform.semicolon_after == 0
