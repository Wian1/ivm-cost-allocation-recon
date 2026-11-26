import os

import streamlit as st

from core import exporters
from core.runs import FILES
from ui_common import require_result

st.title('4. Export')
res = require_result()
run_dir = st.session_state['run_dir']
st.write(f'Everything is already saved in the run folder: `{run_dir}`')
st.caption('Each run gets its own timestamped folder with a `run_metadata.json` (input file names, sizes, '
           'SHA-256 hashes, row counts, mode, tolerances and summary counts) so it can be audited and reproduced.')


def size(p):
    return f'{os.path.getsize(p) / 1e6:,.1f} MB' if os.path.exists(p) else 'not created'


def dl(label, key, mime):
    p = os.path.join(run_dir, FILES[key])
    if os.path.exists(p):
        with open(p, 'rb') as f:
            st.download_button(f'{label} ({size(p)})', f.read(), file_name=FILES[key], mime=mime, key=key)


c = st.columns(2)
with c[0]:
    st.subheader('Reconciliation')
    dl('Reconciliation CSV', 'recon_csv', 'text/csv')
    dl('Reconciliation workbook (Excel, with issues sheets)', 'recon_xlsx',
       'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
with c[1]:
    st.subheader('Log')
    dl('Log (text)', 'log', 'text/plain')
    dl('Warnings (structured CSV)', 'warnings', 'text/csv')
    dl('Run metadata (JSON)', 'meta', 'application/json')

st.subheader('Transformed TABLE 4 (large)')
csv_p, pq_p = os.path.join(run_dir, FILES['table4_csv']), os.path.join(run_dir, FILES['table4_parquet'])
st.write(f'CSV: `{csv_p}` - {size(csv_p)}')
st.write(f'Parquet: `{pq_p}` - {size(pq_p)}')
if not os.path.exists(pq_p) and st.button('Create Parquet version now'):
    with st.spinner('Writing Parquet...'):
        exporters.write_parquet(res.transform.t4, pq_p)
    st.rerun()
st.caption('These files are big, so they are saved to the run folder rather than pushed through the browser. '
           'Tick below only if you really want a browser download.')
if st.checkbox('Prepare browser download of the large file(s) (loads them into memory)'):
    dl('Transformed TABLE 4 (CSV)', 'table4_csv', 'text/csv')
    dl('Transformed TABLE 4 (Parquet)', 'table4_parquet', 'application/octet-stream')
