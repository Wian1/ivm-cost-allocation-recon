"""Run log: plain text lines (like the original transform.log) plus structured warnings."""
from __future__ import annotations

import pandas as pd

STEPS = [
    'Load data',
    'Build invoice lookup',
    'Scan for multi-invoice cells',
    'Add extra columns',
    'Recalculate charges',
    'Check no semicolons remain',
    'Write transformed TABLE 4',
    'Build reconciliation',
]

WARNING_COLUMNS = ['kind', 'category', 'invoice_id', 'bag_id', 'amount', 'message']

# Human-readable names for warning kinds (used in the UI filter)
KIND_LABELS = {
    'missing_column': 'Missing column',
    'duplicate_invoice_t1': 'Duplicate invoice ID in TABLE 1',
    'invoice_not_in_t1': 'Invoice not in TABLE 1 (bag skipped)',
    'zero_tonnage': 'Zero tonnage on invoice',
    'validation_bag': 'Bag-level check failed',
    'validation_inv': 'Invoice-level check failed',
    'recon_not_in_t1': 'Reconciled invoice not in TABLE 1',
    'semicolon_remaining': 'Semicolons remain',
    'row_count': 'Row count changed',
    'column_skipped': 'Category skipped',
    'other': 'Other',
}


class RunLog:
    def __init__(self):
        self.lines: list[str] = []
        self.warnings: list[dict] = []

    def info(self, msg: str):
        self.lines.append(f'INFO: {msg}')

    def warn(self, kind: str, msg: str, category: str = '', invoice_id: str = '',
             bag_id: str = '', amount: float | None = None):
        self.lines.append(f'WARNING: {msg}')
        self.warnings.append({'kind': kind, 'category': category, 'invoice_id': invoice_id,
                              'bag_id': bag_id, 'amount': amount, 'message': msg})

    def warn_many(self, records: list[dict]):
        for r in records:
            self.warn(**r)

    def warnings_frame(self) -> pd.DataFrame:
        if not self.warnings:
            return pd.DataFrame(columns=WARNING_COLUMNS)
        df = pd.DataFrame(self.warnings, columns=WARNING_COLUMNS)
        df['kind_label'] = df['kind'].map(KIND_LABELS).fillna(df['kind'])
        return df

    def text(self) -> str:
        return '\n'.join(self.lines) + '\n'
