"""End-to-end run: load -> transform -> reconcile. UI-free."""
from __future__ import annotations

import os
from dataclasses import dataclass

import pandas as pd

from .loaders import convert_t1, convert_t4, load_t1, load_t4
from .reconcile import classify_issues, reconcile
from .runlog import RunLog
from .transform import Settings, TransformResult, transform_table4, _noop_progress


@dataclass
class RunResult:
    transform: TransformResult
    recon: pd.DataFrame
    issues: dict
    log: RunLog
    settings: Settings
    n_t1: int


def run_frames(t1_raw: pd.DataFrame, t4_raw: pd.DataFrame, settings: Settings,
               progress=_noop_progress, out_t4_csv: str | None = None,
               log: RunLog | None = None) -> RunResult:
    """Run the whole workflow on already-read (all-text) frames.

    If out_t4_csv is given, step 7 writes the transformed TABLE 4 there."""
    log = log or RunLog()
    progress(1, 'Converting numeric columns', None)
    t1 = convert_t1(t1_raw, warn=lambda k, m: log.warn(k, m))
    t4 = convert_t4(t4_raw, warn=lambda k, m: log.warn(k, m))
    log.info(f'TABLE1: {len(t1)} rows  |  TABLE4: {len(t4)} rows')

    res = transform_table4(t1, t4, settings, log, progress)

    progress(7, 'Writing transformed TABLE 4', None)
    if out_t4_csv:
        res.t4.to_csv(out_t4_csv, index=False)
        log.info(f'Transformed TABLE4 written -> {out_t4_csv}')

    progress(8, 'Building reconciliation', None)
    recon = reconcile(res.t4, res.lookup, res.max_ids, settings, log)
    issues = classify_issues(recon, log.warnings_frame(), res.bag_failures, settings)

    n_val_inv = int((recon['Difference ($)'].abs() > settings.inv_tol).sum())
    log.info('=' * 60)
    log.info('SUMMARY')
    log.info(f'  Rows processed               : {res.rows_in}')
    log.info(f'  Semicolon cells before       : {res.semicolon_before}')
    log.info(f'  Semicolon cells after        : {res.semicolon_after}')
    log.info(f'  Bag-level validation failures: {len(res.bag_failures)}')
    log.info(f'  Invoice-level val. failures  : {n_val_inv}')
    log.info(f'  Reconciliation rows          : {len(recon)}')
    log.info('=' * 60)
    log.info('Done.')
    progress(8, 'Done', 1.0)
    return RunResult(res, recon, issues, log, settings, len(t1))


def run_files(t1_path: str, t4_path: str, settings: Settings, progress=_noop_progress,
              out_t4_csv: str | None = None) -> RunResult:
    progress(1, 'Reading TABLE 1', None)
    t1 = load_t1(t1_path)
    progress(1, 'Reading TABLE 4 (large file - this can take a minute)', None)
    t4 = load_t4(t4_path)
    return run_frames(t1, t4, settings, progress, out_t4_csv)
