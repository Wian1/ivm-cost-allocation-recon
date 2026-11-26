"""Create the ~2,000-row TABLE 4 slice used by the regression tests, and run the ORIGINAL
script on it (default + full-recalc) to produce golden files.  Run once:
    py -3.12 tests/make_samples.py
"""
import os, subprocess, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REF = os.path.join(ROOT, 'references')
DATA = os.path.join(ROOT, 'tests', 'data')
sys.path.insert(0, REF)
import transform_table4 as T

t4 = pd.read_csv(os.path.join(REF, 'BAG - COST ALLOCATION - TABLE 4.csv'), dtype=str)
t1 = pd.read_csv(os.path.join(REF, 'INVOICE - COST ALLOCATION - TABLE 1.csv'), dtype=str)
inv_cols = [c['inv_id_col'] for c in T.CATEGORY_CONFIG]
has_semi = pd.Series(False, index=t4.index)
keep = set()
for c in inv_cols:
    s = t4[c].fillna('')
    m = s.str.contains(';', regex=False)
    has_semi |= m
    n = s.str.count(';') + 1
    if m.any():
        keep |= set(n[m][n[m] == n[m].max()].index[:3])      # rows holding the max #ids
rng = np.random.default_rng(42)
semi_idx = np.array([i for i in t4.index[has_semi] if i not in keep])
plain_idx = t4.index[~has_semi].to_numpy()
pick = set(keep) | set(rng.choice(semi_idx, 1300, replace=False)) | set(rng.choice(plain_idx, 700, replace=False))
sample = t4.loc[sorted(pick)]
os.makedirs(os.path.join(DATA, 'golden_default'), exist_ok=True)
os.makedirs(os.path.join(DATA, 'golden_fullrecalc'), exist_ok=True)
sample.to_csv(os.path.join(DATA, 'table4_sample.csv'), index=False)
t1.to_csv(os.path.join(DATA, 'table1.csv'), index=False)
print('sample rows', len(sample))
for name, extra in [('golden_default', []), ('golden_fullrecalc', ['--full-recalc'])]:
    d = os.path.join(DATA, name)
    subprocess.run([sys.executable, os.path.join(REF, 'transform_table4.py'),
                    '--table1', os.path.join(DATA, 'table1.csv'),
                    '--table4', os.path.join(DATA, 'table4_sample.csv'),
                    '--out-table4', os.path.join(d, 'table4_transformed.csv'),
                    '--out-recon', os.path.join(d, 'reconciliation.csv'),
                    '--log', os.path.join(d, 'transform.log')] + extra,
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print('golden', name, 'done')
