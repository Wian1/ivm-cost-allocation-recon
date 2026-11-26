import json
import os

import pandas as pd
import streamlit as st

from core.reconcile import RECON_COLUMNS
from core.runs import FILES, compare_runs, list_runs, load_recon
from ui_common import money, style_recon

st.title('5. Run history')
runs = [r for r in list_runs()]
done = [r for r in runs if r['complete']]
if not runs:
    st.info('No runs yet. Runs are saved in the `runs/` folder, one timestamped folder per run.')
    st.stop()

rows = []
for r in runs:
    m = r.get('meta', {})
    sm = m.get('summary', {})
    rows.append({'Run': r['name'], 'Status': 'Complete' if r['complete'] else 'Incomplete (no metadata)',
                 'Mode': m.get('mode', ''), 'Bag rows': sm.get('rows_in'), 'Recon rows': sm.get('reconciliation_rows'),
                 'Match': sm.get('match'), 'Mismatch': sm.get('mismatch'),
                 'Net difference ($)': sm.get('net_difference'),
                 'Match tolerance ($)': m.get('tolerances', {}).get('match')})
st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

tab_open, tab_cmp = st.tabs(['Open a run', 'Compare two runs'])
names = [r['name'] for r in done]
by_name = {r['name']: r for r in done}

with tab_open:
    if not names:
        st.info('No complete runs to open.')
    else:
        pick = st.selectbox('Run', names)
        r = by_name[pick]
        m = r['meta']
        st.write(f'Folder: `{r["path"]}`')
        with st.expander('Run metadata (inputs, hashes, tolerances, summary)'):
            st.json(m)
        rec = load_recon(r['path'])
        st.dataframe(style_recon(rec[RECON_COLUMNS].assign(_a=rec['Difference ($)'].abs())
                                 .sort_values('_a', ascending=False, na_position='first').drop(columns='_a')),
                     use_container_width=True, hide_index=True, height=420)
        for key, label in [('recon_xlsx', 'Excel workbook'), ('recon_csv', 'Reconciliation CSV'), ('log', 'Log')]:
            p = os.path.join(r['path'], FILES[key])
            if os.path.exists(p):
                with open(p, 'rb') as f:
                    st.download_button(label, f.read(), file_name=FILES[key], key=f'h_{key}')

with tab_cmp:
    if len(names) < 2:
        st.info('You need at least two complete runs to compare.')
    else:
        c = st.columns(2)
        a = c[0].selectbox('Run A (older)', names, index=min(1, len(names) - 1))
        b = c[1].selectbox('Run B (newer)', names, index=0)
        if a == b:
            st.warning('Pick two different runs.')
        else:
            ma, mb = by_name[a]['meta'], by_name[b]['meta']
            if ma.get('tolerances') != mb.get('tolerances') or ma.get('mode') != mb.get('mode'):
                st.warning(f'The runs used different settings (A: {ma.get("mode")} / {ma.get("tolerances")}; '
                           f'B: {mb.get("mode")} / {mb.get("tolerances")}). Match status differences may come '
                           f'from the settings rather than the data.')
            for k in ('table1', 'table4'):
                if ma['inputs'][k].get('sha256') != mb['inputs'][k].get('sha256'):
                    st.info(f'{k.upper()} input file differs between the runs.')
            cmp = compare_runs(load_recon(by_name[a]['path']), load_recon(by_name[b]['path']))
            counts = cmp['Change'].value_counts()
            cols = st.columns(5)
            for col, lab in zip(cols, ['Match status changed', 'Difference changed', 'Only in run A',
                                       'Only in run B', 'Unchanged']):
                col.metric(lab, f'{int(counts.get(lab, 0)):,}')
            show = st.multiselect('Show', list(counts.index),
                                  default=[x for x in counts.index if x != 'Unchanged'])
            v = cmp[cmp['Change'].isin(show)] if show else cmp
            st.dataframe(v, use_container_width=True, hide_index=True, height=480)
