"""Unit tests for edge cases, using tiny synthetic tables."""
import numpy as np
import pandas as pd
import pytest

from core.pipeline import run_frames
from core.reconcile import NOT_IN_T1
from core.transform import Settings

RL_ID, RL_CHG, RL_T1 = ('RECEPTION LOGISTICS INVOICE ID.', 'RECEPTION LOGISTICS CHARGE ($)',
                        'RECEPTION LOGISTICS ($)')
DM_ID, DM_CHG, DM_T1 = 'DEMURRAGE TRUCK INVOICE ID.', 'DEMURRAGE TRUCK CHARGE ($)', 'DEMURRAGE TRUCK ($)'
TON = 'PORT WAREHOUSE NET WEIGHT (TONS)'


def t1_frame(rows):
    """rows: list of (invoice_id, {t1 col: amount})"""
    recs = []
    for inv, vals in rows:
        recs.append({'INVOICE ID.': inv, 'LSP NAME': 'LSP', 'AOC VESSEL NAME': 'V', **vals})
    return pd.DataFrame(recs)


def t4_frame(rows):
    """rows: list of dicts with BAG ID and any of RL_ID, RL_CHG, TON, DM_ID, DM_CHG"""
    df = pd.DataFrame(rows)
    for c in (RL_ID, DM_ID):
        if c not in df:
            df[c] = np.nan
    for c in (RL_CHG, DM_CHG, TON):
        if c not in df:
            df[c] = np.nan
        df[c] = df[c].astype(float)
    return df


def run(t1, t4, **kw):
    return run_frames(t1, t4, Settings(**kw))


def cell(res, row, col):
    return res.transform.t4.loc[row, col]


def test_single_id_default_keeps_charge_but_normalises_id():
    t1 = t1_frame([('A1', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: ' a1 ', RL_CHG: 77.0, TON: 2.0}])
    r = run(t1, t4)
    assert cell(r, 0, RL_ID) == 'A1'
    assert cell(r, 0, RL_CHG) == 77.0          # untouched in default mode


def test_single_id_full_recalc_overwrites_charge():
    t1 = t1_frame([('A1', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A1', RL_CHG: 77.0, TON: 2.0},
                   {'BAG ID': 'b2', RL_ID: 'A1', RL_CHG: 1.0, TON: 3.0}])
    r = run(t1, t4, full_recalc=True)
    assert cell(r, 0, RL_CHG) == pytest.approx(40.0)
    assert cell(r, 1, RL_CHG) == pytest.approx(60.0)


def test_many_ids_creates_overflow_columns_and_rate_times_tonnage():
    t1 = t1_frame([('A', {RL_T1: 100.0}), ('B', {RL_T1: 50.0}), ('C', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; B; C', RL_CHG: 160.0, TON: 2.0},
                   {'BAG ID': 'b2', RL_ID: 'A', RL_CHG: 0.0, TON: 8.0}])
    r = run(t1, t4)
    out = r.transform.t4
    assert r.transform.max_ids[RL_ID] == 3
    assert [RL_ID + '_2', RL_ID + '_3'] == [c for c in out.columns if c.startswith(RL_ID + '_')]
    cols = list(out.columns)
    assert cols.index(RL_CHG + '_2') == cols.index(RL_CHG) + 1
    assert cols.index(RL_ID + '_2') == cols.index(RL_ID) + 1
    # rate A = 100 / (2+8) = 10/t -> 20 ; B = 50/2 = 25/t -> 50 ; C = 10/2 -> 10
    assert cell(r, 0, RL_CHG) == pytest.approx(20.0)
    assert cell(r, 0, RL_CHG + '_2') == pytest.approx(50.0)
    assert cell(r, 0, RL_CHG + '_3') == pytest.approx(10.0)
    assert (cell(r, 0, RL_ID), cell(r, 0, RL_ID + '_2'), cell(r, 0, RL_ID + '_3')) == ('A', 'B', 'C')
    assert r.transform.semicolon_before == 1 and r.transform.semicolon_after == 0


def test_denominator_is_table4_tonnage_not_table1():
    t1 = t1_frame([('A', {RL_T1: 90.0, 'PORT WHS NET WEIGHT (KG)': 999999.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; B', RL_CHG: 0.0, TON: 1.0},
                   {'BAG ID': 'b2', RL_ID: 'A', RL_CHG: 0.0, TON: 2.0}])
    r = run(t1, t4)
    assert cell(r, 0, RL_CHG) == pytest.approx(30.0)      # 90 / 3t * 1t


def test_duplicate_ids_in_one_cell_each_counted():
    t1 = t1_frame([('A', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; A', RL_CHG: 0.0, TON: 5.0}])
    r = run(t1, t4)
    # tonnage sum counts the bag twice (original behaviour): rate = 100/10, each occurrence 50
    assert cell(r, 0, RL_CHG) == pytest.approx(50.0)
    assert cell(r, 0, RL_CHG + '_2') == pytest.approx(50.0)
    assert r.transform.max_ids[RL_ID] == 2


@pytest.mark.parametrize('raw', ['A;B;', ' ;A;;B ', 'a ; b', 'A;b;nan'])
def test_trailing_semicolons_whitespace_and_case(raw):
    t1 = t1_frame([('A', {RL_T1: 10.0}), ('B', {RL_T1: 20.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: raw, RL_CHG: 0.0, TON: 1.0}])
    r = run(t1, t4)
    assert r.transform.max_ids[RL_ID] == 2
    assert (cell(r, 0, RL_ID), cell(r, 0, RL_ID + '_2')) == ('A', 'B')
    assert r.transform.semicolon_after == 0


def test_second_invoice_missing_from_table1_is_skipped_with_warning():
    t1 = t1_frame([('A', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; ZZZ', RL_CHG: 10.0, TON: 1.0}])
    r = run(t1, t4)
    assert cell(r, 0, RL_ID + '_2') == '' and np.isnan(cell(r, 0, RL_CHG + '_2'))
    w = r.log.warnings_frame()
    assert ((w['kind'] == 'invoice_not_in_t1') & (w['invoice_id'] == 'ZZZ') & (w['bag_id'] == 'b1')).any()


def test_first_invoice_missing_leaves_cell_with_semicolon_and_is_reported():
    t1 = t1_frame([('B', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'ZZZ; B', RL_CHG: 10.0, TON: 1.0}])
    r = run(t1, t4)
    assert cell(r, 0, RL_ID) == 'ZZZ; B'           # original behaviour, kept
    assert r.transform.semicolon_after == 1
    assert (r.log.warnings_frame()['kind'] == 'semicolon_remaining').any()


def test_zero_tonnage_forces_zero_and_warns():
    t1 = t1_frame([('A', {RL_T1: 100.0}), ('B', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; B', RL_CHG: 5.0, TON: 0.0}])
    r = run(t1, t4)
    assert cell(r, 0, RL_CHG) == 0.0 and cell(r, 0, RL_CHG + '_2') == 0.0
    w = r.log.warnings_frame()
    assert (w['kind'] == 'zero_tonnage').sum() == 2
    assert r.issues['zero_tonnage']['count'] == 2


def test_per_bag_demurrage():
    t1 = t1_frame([('D1', {DM_T1: 300.0}), ('D2', {DM_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', DM_ID: 'D1; D2', DM_CHG: 0.0, TON: 1.0},
                   {'BAG ID': 'b2', DM_ID: 'D1', DM_CHG: 0.0, TON: 50.0},
                   {'BAG ID': 'b3', DM_ID: 'D1', DM_CHG: 0.0, TON: 1.0}])
    r = run(t1, t4)
    assert cell(r, 0, DM_CHG) == pytest.approx(100.0)          # 300 / 3 bags, tonnage irrelevant
    assert cell(r, 0, DM_CHG + '_2') == pytest.approx(100.0)   # 100 / 1 bag


def test_reconciliation_includes_invoices_without_bags_and_unknown_invoices():
    t1 = t1_frame([('A', {RL_T1: 10.0}), ('NOBAGS', {RL_T1: 500.0}), ('ZERO', {RL_T1: 0.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A', RL_CHG: 10.0, TON: 1.0},
                   {'BAG ID': 'b2', RL_ID: 'UNKNOWN', RL_CHG: 3.0, TON: 1.0}])
    r = run(t1, t4)
    rc = r.recon.set_index('Invoice ID')
    assert rc.loc['A', 'Match?'] == 'Match'
    assert rc.loc['NOBAGS', 'Total Cost Allocated to Bags ($)'] == 0.0
    assert rc.loc['NOBAGS', 'Match?'] == 'Mismatch' and rc.loc['NOBAGS', 'Difference ($)'] == -500.0
    assert rc.loc['UNKNOWN', 'Match?'] == NOT_IN_T1
    assert 'ZERO' not in rc.index                      # zero amount and no bags: not listed
    assert r.issues['no_bags']['count'] == 1 and r.issues['not_in_t1']['count'] == 1


@pytest.mark.parametrize('bag_total,expected', [(100.0, 'Match'), (101.0, 'Match'), (99.0, 'Match'),
                                                 (101.01, 'Mismatch'), (98.99, 'Mismatch')])
def test_match_tolerance_is_one_dollar_inclusive(bag_total, expected):
    t1 = t1_frame([('A', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A', RL_CHG: bag_total, TON: 1.0}])
    assert run(t1, t4).recon.iloc[0]['Match?'] == expected


def test_match_tolerance_is_configurable():
    t1 = t1_frame([('A', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A', RL_CHG: 100.5, TON: 1.0}])
    assert run(t1, t4, match_tol=0.01).recon.iloc[0]['Match?'] == 'Mismatch'


def test_difference_sign_is_bags_minus_invoice():
    t1 = t1_frame([('A', {RL_T1: 100.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A', RL_CHG: 150.0, TON: 1.0}])
    assert run(t1, t4).recon.iloc[0]['Difference ($)'] == 50.0


def test_duplicate_invoice_ids_in_table1_warn_and_last_wins():
    t1 = t1_frame([('A', {RL_T1: 10.0}), ('a ', {RL_T1: 99.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; A', RL_CHG: 0.0, TON: 1.0}])
    r = run(t1, t4)
    assert (r.log.warnings_frame()['kind'] == 'duplicate_invoice_t1').any()
    assert r.recon.iloc[0]['Total Invoice Amount ($)'] == 99.0


def test_bag_level_validation_flags_when_sum_differs_from_original():
    t1 = t1_frame([('A', {RL_T1: 10.0}), ('B', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'A; B', RL_CHG: 10.0, TON: 1.0},     # ok: 5+5
                   {'BAG ID': 'b2', RL_ID: 'A; B', RL_CHG: 99.0, TON: 1.0}])    # bad
    r = run(t1, t4)
    assert list(r.transform.bag_failures['Bag ID']) == ['b2']
    assert r.issues['bag_validation']['count'] == 1


def test_credit_notes_flagged_in_no_bag_issue():
    t1 = t1_frame([('CR', {RL_T1: -40.0}), ('INV', {RL_T1: 60.0})])
    t4 = t4_frame([{'BAG ID': 'b1', RL_ID: 'X', RL_CHG: 1.0, TON: 1.0}])
    iss = run(t1, t4).issues['no_bags']
    assert iss['count'] == 2 and iss['extra']['credit_count'] == 1
    assert iss['extra']['net'] == pytest.approx(20.0) and iss['extra']['gross'] == pytest.approx(100.0)


def test_row_count_preserved_and_input_not_mutated():
    t1 = t1_frame([('A', {RL_T1: 10.0})])
    t4 = t4_frame([{'BAG ID': f'b{i}', RL_ID: 'A; A' if i % 2 else 'A', RL_CHG: 1.0, TON: 1.0}
                   for i in range(10)])
    before = t4.copy()
    r = run(t1, t4)
    assert r.transform.rows_in == r.transform.rows_out == 10
    pd.testing.assert_frame_equal(t4, before)
