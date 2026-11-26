"""CSV / Parquet / Excel / log exports and run metadata. UI-free."""
from __future__ import annotations

import json
import os
import platform
from datetime import datetime

import pandas as pd

from .pipeline import RunResult
from .reconcile import RECON_COLUMNS

EXCEL_MAX_ROWS = 1_000_000


def summary_counts(res: RunResult) -> dict:
    r = res.recon
    t = res.transform
    inv = pd.to_numeric(r['Total Invoice Amount ($)'], errors='coerce')
    return {
        'rows_in': t.rows_in, 'rows_out': t.rows_out,
        'invoices_in_table1': res.n_t1,
        'semicolon_cells_before': t.semicolon_before, 'semicolon_cells_after': t.semicolon_after,
        'reconciliation_rows': len(r),
        'match': int((r['Match?'] == 'Match').sum()),
        'mismatch': int((r['Match?'] == 'Mismatch').sum()),
        'not_in_table1': int(r['Match?'].str.startswith('?').sum()),
        'total_invoiced': round(float(inv.sum()), 2),
        'total_allocated': round(float(r['Total Cost Allocated to Bags ($)'].sum()), 2),
        'net_difference': round(float(r['Difference ($)'].sum()), 2),
        'bag_validation_failures': len(t.bag_failures),
        'invoice_validation_failures': int((r['Difference ($)'].abs() > res.settings.inv_tol).sum()),
        'overflow_columns_added': int(sum(2 * (m - 1) for m in t.max_ids.values())),
        'issues': {k: {'count': v['count'], 'impact': round(v['impact'], 2)} for k, v in res.issues.items()},
    }


def write_metadata(path: str, res: RunResult, inputs: dict, extra: dict | None = None):
    meta = {
        'created': datetime.now().isoformat(timespec='seconds'),
        'inputs': inputs,                       # {'table1': fingerprint, 'table4': fingerprint}
        'mode': 'full_recalc' if res.settings.full_recalc else 'default',
        'tolerances': {'bag_validation': res.settings.bag_tol,
                       'invoice_validation': res.settings.inv_tol,
                       'match': res.settings.match_tol},
        'summary': summary_counts(res),
        'python': platform.python_version(), 'pandas': pd.__version__,
    }
    if extra:
        meta.update(extra)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(meta, f, indent=2)
    return meta


def write_parquet(t4: pd.DataFrame, path: str):
    t4.to_parquet(path, index=False)


def write_recon_csv(recon: pd.DataFrame, path: str):
    recon[RECON_COLUMNS].to_csv(path, index=False)


def write_log(path: str, res: RunResult):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(res.log.text())
    res.log.warnings_frame().to_csv(os.path.splitext(path)[0] + '_warnings.csv', index=False)


def write_excel(path: str, res: RunResult):
    r = res.recon
    s = summary_counts(res)
    with pd.ExcelWriter(path, engine='xlsxwriter') as xw:
        wb = xw.book
        hdr = wb.add_format({'bold': True, 'bg_color': '#1F3A5F', 'font_color': 'white', 'border': 1})
        money = wb.add_format({'num_format': '#,##0.00;[Red]-#,##0.00'})
        red = wb.add_format({'bg_color': '#F8D7DA', 'font_color': '#7A1F2B'})
        amber = wb.add_format({'bg_color': '#FFF3CD', 'font_color': '#664D03'})

        def put(df, name, money_cols=()):
            df = df.iloc[:EXCEL_MAX_ROWS - 1]
            df.to_excel(xw, sheet_name=name[:31], index=False)
            ws = xw.sheets[name[:31]]
            for i, c in enumerate(df.columns):
                ws.write(0, i, c, hdr)
                width = min(48, max(10, int(df[c].astype(str).str.len().quantile(.95)) + 2 if len(df) else 10,
                                    len(str(c)) + 2))
                ws.set_column(i, i, width, money if c in money_cols else None)
            ws.freeze_panes(1, 0)
            ws.autofilter(0, 0, max(len(df), 1), max(len(df.columns) - 1, 0))
            return ws

        # Summary
        rows = [('Run created', datetime.now().strftime('%Y-%m-%d %H:%M:%S')),
                ('Mode', 'Full recalculation' if res.settings.full_recalc else 'Default (multi-invoice rows only)'),
                ('Match tolerance ($)', res.settings.match_tol),
                ('Bag check tolerance ($)', res.settings.bag_tol),
                ('Invoice check tolerance ($)', res.settings.inv_tol),
                ('Bag rows in', s['rows_in']), ('Bag rows out', s['rows_out']),
                ('Semicolon cells before', s['semicolon_cells_before']),
                ('Semicolon cells after', s['semicolon_cells_after']),
                ('Reconciliation rows', s['reconciliation_rows']),
                ('Match', s['match']), ('Mismatch', s['mismatch']),
                ('Invoice not in TABLE 1', s['not_in_table1']),
                ('Total invoiced ($)', s['total_invoiced']),
                ('Total allocated to bags ($)', s['total_allocated']),
                ('Net difference ($)', s['net_difference'])]
        pd.DataFrame(rows, columns=['Item', 'Value']).to_excel(xw, sheet_name='Summary', index=False)
        ws = xw.sheets['Summary']
        ws.set_column(0, 0, 36); ws.set_column(1, 1, 34)
        for i, c in enumerate(['Item', 'Value']):
            ws.write(0, i, c, hdr)

        # Reconciliation
        ws = put(r[RECON_COLUMNS], 'Reconciliation',
                 ['Total Cost Allocated to Bags ($)', 'Total Invoice Amount ($)', 'Difference ($)'])
        last = max(len(r), 1)
        ws.conditional_format(1, 0, last, len(RECON_COLUMNS) - 1,
                              {'type': 'formula', 'criteria': '=$H2="Mismatch"', 'format': red})
        ws.conditional_format(1, 0, last, len(RECON_COLUMNS) - 1,
                              {'type': 'formula', 'criteria': '=LEFT($H2,1)="?"', 'format': amber})

        # Issues overview + one sheet per issue
        ov = pd.DataFrame([{'Issue': v['title'], 'Count': v['count'], 'Impact ($)': round(v['impact'], 2),
                            'Impact measure': v['impact_label'], 'What it means': v['help']}
                           for v in res.issues.values()])
        put(ov, 'Issues overview', ['Impact ($)'])
        sheet_names = {'no_bags': 'Issue - No bags', 'not_in_t1': 'Issue - Not in TABLE1',
                       'rounding': 'Issue - Within tolerance', 'material': 'Issue - Material diff',
                       'zero_tonnage': 'Issue - Zero tonnage', 'bag_validation': 'Issue - Bag checks'}
        for k, v in res.issues.items():
            if v['count']:
                df = v['df'].drop(columns=['Bags Referencing Invoice'], errors='ignore') \
                    if k != 'no_bags' else v['df']
                put(df, sheet_names[k], [c for c in df.columns if '($)' in c])

        # Warnings
        w = res.log.warnings_frame()
        if len(w):
            put(w[['kind_label', 'category', 'invoice_id', 'bag_id', 'amount', 'message']]
                .rename(columns={'kind_label': 'Type', 'category': 'Category', 'invoice_id': 'Invoice',
                                 'bag_id': 'Bag', 'amount': 'Amount ($)', 'message': 'Message'}),
                'Warnings')
