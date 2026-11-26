"""Read, validate and type-convert the two input CSVs. UI-free."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field

import pandas as pd

from .config import (
    CATEGORY_CONFIG, PASS_THROUGH_T4, T1_CHARGE_COLS, T1_ID_COL, T1_WEIGHT_COLS,
    T4_BAG_COL, T4_WEIGHT_COLS,
)


class InputError(Exception):
    """Raised for malformed input files. The message is user-facing."""


def file_fingerprint(path: str, full_hash: bool = True) -> dict:
    """Name, size and SHA-256 of a file (used for run metadata)."""
    st = os.stat(path)
    info = {'name': os.path.basename(path), 'path': os.path.abspath(path), 'size_bytes': st.st_size}
    if full_hash:
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
                h.update(chunk)
        info['sha256'] = h.hexdigest()
    return info


def _sniff_header(path: str) -> tuple[str, str]:
    """Return (encoding, header_line). Raises InputError for empty / unreadable files."""
    if not os.path.exists(path):
        raise InputError(f'File not found: {path}')
    if os.path.getsize(path) == 0:
        raise InputError(f'File is empty: {os.path.basename(path)}')
    for enc in ('utf-8-sig', 'cp1252'):
        try:
            with open(path, 'r', encoding=enc, newline='') as f:
                header = f.readline()
            if enc == 'utf-8-sig':
                # make sure the rest decodes too (cheap check on first 1 MB)
                with open(path, 'r', encoding=enc) as f:
                    f.read(1024 * 1024)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise InputError(f'Cannot decode {os.path.basename(path)} (tried UTF-8 and Windows-1252).')
    if not header.strip():
        raise InputError(f'First line of {os.path.basename(path)} is blank - expected a header row.')
    return enc, header


def read_csv_strict(path: str, label: str) -> pd.DataFrame:
    """Read a CSV with every column as text (numeric conversion happens afterwards)."""
    enc, header = _sniff_header(path)
    commas, semis, tabs = header.count(','), header.count(';'), header.count('\t')
    if commas == 0 and (semis > 0 or tabs > 0):
        delim = 'semicolon' if semis >= tabs else 'tab'
        raise InputError(
            f'{label}: the file looks {delim}-delimited, but a comma-delimited CSV is expected. '
            f'Re-export it as a comma-separated CSV.')
    if commas == 0:
        raise InputError(f'{label}: no comma found in the header row - this does not look like a CSV.')
    try:
        df = pd.read_csv(path, dtype=str, encoding=enc)
    except pd.errors.EmptyDataError:
        raise InputError(f'{label}: file has no data.')
    except pd.errors.ParserError as e:
        raise InputError(f'{label}: could not parse the CSV ({e}).')
    if len(df) == 0:
        raise InputError(f'{label}: the file has a header but no data rows.')
    return df


def convert_t1(t1: pd.DataFrame, warn=None) -> pd.DataFrame:
    """Numeric conversion of TABLE 1 charge / weight columns (as the original script)."""
    t1 = t1.copy()
    for col in T1_CHARGE_COLS + T1_WEIGHT_COLS:
        if col in t1.columns:
            t1[col] = pd.to_numeric(t1[col], errors='coerce')
        elif warn:
            warn('missing_column', f'TABLE1 missing expected column: {col!r}')
    return t1


def convert_t4(t4: pd.DataFrame, warn=None) -> pd.DataFrame:
    """Numeric conversion of TABLE 4 charge / weight columns (as the original script)."""
    t4 = t4.copy()
    charge_cols = [c['charge_col'] for c in CATEGORY_CONFIG]
    for col in charge_cols + T4_WEIGHT_COLS:
        if col in t4.columns:
            t4[col] = pd.to_numeric(t4[col], errors='coerce').astype('float64')
        elif warn:
            warn('missing_column', f'TABLE4 missing expected column: {col!r}')
    return t4


def load_t1(path: str) -> pd.DataFrame:
    return read_csv_strict(path, 'TABLE 1 (invoice)')


def load_t4(path: str) -> pd.DataFrame:
    return read_csv_strict(path, 'TABLE 4 (bag)')


# ---------------------------------------------------------------------------
# Schema check
# ---------------------------------------------------------------------------
@dataclass
class CategorySchema:
    label: str
    display_label: str
    method: str
    missing_t4: list[str] = field(default_factory=list)
    missing_t1: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not (self.missing_t4 or self.missing_t1)


@dataclass
class SchemaReport:
    categories: list[CategorySchema]
    missing_global: list[str]          # e.g. INVOICE ID. missing from TABLE 1
    pass_through: list[tuple[str, bool]]   # (column, present in TABLE 4)
    warnings: list[str]

    @property
    def can_run(self) -> bool:
        return not self.missing_global and all(c.ok for c in self.categories)

    def to_frame(self) -> pd.DataFrame:
        rows = []
        for c in CATEGORY_CONFIG:
            s = next(x for x in self.categories if x.label == c['label'])
            rows.append({
                'Category': c['display_label'],
                'Method': 'Per bag' if s.method == 'per_bag' else 'Rate x tonnage',
                'TABLE 4 invoice ID column': c['inv_id_col'],
                'TABLE 4 charge column': c['charge_col'],
                'TABLE 4 tonnage column': c['t4_tonnage'],
                'TABLE 1 amount column': c['t1_charge'],
                'Status': 'OK' if s.ok else 'MISSING: ' + '; '.join(s.missing_t4 + s.missing_t1),
            })
        return pd.DataFrame(rows)


def check_schema(t1_cols, t4_cols) -> SchemaReport:
    t1_cols, t4_cols = set(t1_cols), set(t4_cols)
    cats = []
    for cfg in CATEGORY_CONFIG:
        method = cfg.get('recalc_method') or 'rate_x_tonnage'
        m4 = [cfg['inv_id_col'], cfg['charge_col']]
        if method != 'per_bag':
            m4.append(cfg['t4_tonnage'])
        cats.append(CategorySchema(
            cfg['label'], cfg['display_label'], method,
            [c for c in m4 if c not in t4_cols],
            [c for c in [cfg['t1_charge']] if c not in t1_cols]))
    glob = [f'TABLE 1: {T1_ID_COL}'] if T1_ID_COL not in t1_cols else []
    warns = []
    if T4_BAG_COL not in t4_cols:
        warns.append(f'TABLE 4 has no {T4_BAG_COL!r} column - bag numbers in warnings fall back to row numbers.')
    for col in ('LSP NAME', 'AOC VESSEL NAME'):
        if col not in t1_cols:
            warns.append(f'TABLE 1 has no {col!r} column - it will be blank in the reconciliation.')
    return SchemaReport(cats, glob, [(c, c in t4_cols) for c in PASS_THROUGH_T4], warns)
