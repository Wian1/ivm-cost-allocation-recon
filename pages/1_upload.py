import os

import pandas as pd
import streamlit as st

from core.config import PASS_THROUGH_T4
from core.loaders import InputError
from ui_common import (UPLOAD_DIR, default_input_dir, file_sig, load_pair, money, save_input_dir)

st.title('1. Upload & check the input files')
st.write('Load the **invoice table (TABLE 1)** and the **bag table (TABLE 4)**. The app checks the column '
         'names straight away and shows a quick profile before anything is calculated.')

src = st.radio('Where are the files?', ['Pick from a folder on this computer (best for the large bag file)',
                                       'Upload through the browser'], index=0)
t1_path = t4_path = None

if src.startswith('Pick'):
    folder = st.text_input('Folder', value=st.session_state.get('input_dir', default_input_dir()),
                           help='Any folder holding the two CSV exports.')
    st.session_state['input_dir'] = folder
    if not os.path.isdir(folder):
        st.error(f'Folder not found: {folder}')
    else:
        save_input_dir(folder)
        csvs = sorted(f for f in os.listdir(folder) if f.lower().endswith('.csv'))
        if not csvs:
            st.warning('No CSV files in that folder.')
        else:
            def pick(token):
                for i, f in enumerate(csvs):
                    if token in f.upper():
                        return i
                return 0
            c1, c2 = st.columns(2)
            f1 = c1.selectbox('TABLE 1 - invoice file', csvs, index=pick('TABLE 1'))
            f4 = c2.selectbox('TABLE 4 - bag file', csvs, index=pick('TABLE 4'))
            t1_path, t4_path = os.path.join(folder, f1), os.path.join(folder, f4)
            c1.caption(f'{os.path.getsize(t1_path) / 1e6:,.1f} MB')
            c2.caption(f'{os.path.getsize(t4_path) / 1e6:,.1f} MB')
else:
    c1, c2 = st.columns(2)
    u1 = c1.file_uploader('TABLE 1 - invoice CSV', type='csv')
    u4 = c2.file_uploader('TABLE 4 - bag CSV', type='csv')
    if u1 and u4:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        t1_path, t4_path = os.path.join(UPLOAD_DIR, u1.name), os.path.join(UPLOAD_DIR, u4.name)
        for up, p in ((u1, t1_path), (u4, t4_path)):
            if not os.path.exists(p) or os.path.getsize(p) != up.size:
                with open(p, 'wb') as f:
                    f.write(up.getbuffer())

if t1_path and t4_path and st.button('Load and check files', type='primary'):
    try:
        with st.spinner('Reading the files... the 250 MB bag file takes about a minute the first time.'):
            data = load_pair(t1_path, file_sig(t1_path), t4_path, file_sig(t4_path))
        st.session_state['loaded'] = {**data, 't1_path': t1_path, 't4_path': t4_path}
        st.session_state.pop('result', None)
    except InputError as e:
        st.session_state.pop('loaded', None)
        st.error(f'Cannot use these files: {e}')
    except Exception as e:  # noqa: BLE001 - show anything unexpected clearly
        st.session_state.pop('loaded', None)
        st.error(f'Unexpected problem reading the files: {type(e).__name__}: {e}')

loaded = st.session_state.get('loaded')
if loaded:
    schema, prof = loaded['schema'], loaded['profile']
    st.success(f'Loaded **{os.path.basename(loaded["t1_path"])}** and **{os.path.basename(loaded["t4_path"])}**.')

    st.subheader('Column check')
    if schema.missing_global:
        st.error('Required column(s) missing: ' + '; '.join(schema.missing_global))
    bad = [c for c in schema.categories if not c.ok]
    if bad:
        st.error('The run is **blocked**. These categories have missing columns and would be skipped:')
        for c in bad:
            st.write(f'- **{c.display_label}** - missing: ' + '; '.join(
                [f'TABLE 4 `{m}`' for m in c.missing_t4] + [f'TABLE 1 `{m}`' for m in c.missing_t1]))
        st.caption('Column names must match exactly, including known quirks: `PORT WHS STORAGE INVOICE ID` '
                   '(no trailing full stop), `DRAFT SURVERY CHARGE ($)` (spelling) and '
                   '`OTHER LOGISTICS (EX. INLAND)  ($)` in TABLE 1 (two spaces).')
    else:
        st.success(f'All {len(schema.categories)} categories have the columns they need.')
    for w in schema.warnings:
        st.warning(w)
    with st.expander('Expected columns per category (exact names)'):
        st.dataframe(schema.to_frame(), use_container_width=True, hide_index=True)
        st.caption('Quirks kept on purpose: ' 'PORT WHS STORAGE INVOICE ID has no trailing period; '
                   'DRAFT SURVERY CHARGE ($) is misspelled in TABLE 4; the TABLE 1 column '
                   'OTHER LOGISTICS (EX. INLAND)  ($) has two spaces.')
    st.write('**Not reconciled (passed through unchanged):** ' + ', '.join(
        f'{c} {"(present)" if ok else "(not in file)"}' for c, ok in schema.pass_through))

    st.subheader('Quick profile')
    a, b, c, d = st.columns(4)
    a.metric('Bag rows (TABLE 4)', f'{prof["t4_rows"]:,}')
    b.metric('Invoices (TABLE 1)', f'{prof["t1_rows"]:,}')
    c.metric('Unique invoice IDs in TABLE 1', f'{prof["t1_unique_invoices"]:,}')
    d.metric('Invoice IDs referenced by bags', f'{prof["t4_referenced_invoices"]:,}')
    cat = prof['categories']
    a, b, c = st.columns(3)
    a.metric('Cells with several invoice IDs', f'{int(cat["Cells with several invoice IDs"].sum()):,}',
             help='Cells containing a semicolon, e.g. "32470; 25827". These are what the transform splits.')
    b.metric('Extra column pairs to add', f'{int(cat["Extra column pairs to add"].sum()):,}',
             help='Extra column pairs: one invoice-ID column plus one charge column per additional '
                  'invoice on a bag. ' + 'When a bag was covered by several invoices, the extra IDs go in '
                  'new columns so each charge sits against one invoice.')
    c.metric('Duplicate invoice IDs in TABLE 1', len(prof['duplicate_t1_ids']),
             help='If an ID appears twice, the last row is used.')
    if prof['duplicate_t1_ids']:
        st.warning('Duplicate TABLE 1 invoice IDs (last row wins): ' + ', '.join(prof['duplicate_t1_ids'][:30]))
    mw = prof['missing_weights']
    st.write('**Bags with a missing or non-numeric weight:** ' +
             ', '.join(f'{k}: {v:,}' for k, v in mw.items()))
    st.dataframe(cat, use_container_width=True, hide_index=True)
    st.caption(f'Memory: the loaded bag table uses roughly {prof["approx_memory_mb"]:,} MB; expect the run '
               f'to need about 3-4x that while it works (several GB for the full file).')
    if schema.can_run:
        st.page_link('pages/2_run.py', label='Continue to **2. Run**', icon=':material/arrow_forward:')
