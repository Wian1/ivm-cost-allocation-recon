import os
import time

import streamlit as st

from core import exporters
from core.config import DEFAULT_BAG_TOL, DEFAULT_INV_TOL, DEFAULT_MATCH_TOL
from core.loaders import file_fingerprint
from core.pipeline import run_frames
from core.runlog import STEPS
from core.runs import FILES, new_run_dir
from core.transform import Settings
from ui_common import HELP, require_inputs

st.title('2. Run settings')
loaded = require_inputs()
schema = loaded['schema']
if not schema.can_run:
    st.error('A required column is missing, so the run is blocked. See **1. Upload & check**.')
    st.stop()

st.write(f'Files: **{os.path.basename(loaded["t1_path"])}** + **{os.path.basename(loaded["t4_path"])}** '
         f'({loaded["profile"]["t4_rows"]:,} bags, {loaded["profile"]["t1_rows"]:,} invoices)')

mode = st.radio(
    'How should charges be recalculated?',
    ['Default - only bags with several invoice IDs',
     'Full recalculation - every bag that has an invoice ID'],
    help='Default keeps the charge already in TABLE 4 for bags with a single invoice, and only recalculates '
         'bags where several invoices were listed. Full recalculation recalculates every bag from TABLE 1.')
full = mode.startswith('Full')
if full:
    st.warning('**Full recalculation overwrites the existing charges on single-invoice bags** with values '
               'recalculated from TABLE 1. Use it as a one-off check when you suspect the existing charges '
               'are wrong. Results will differ from a default run.')
else:
    st.caption('Bags with one invoice keep their existing charge. Only bags with several invoice IDs '
               '(e.g. "32470; 25827") are split and recalculated.')

with st.expander('Advanced: tolerances'):
    match_tol = st.number_input('Match tolerance ($)', value=DEFAULT_MATCH_TOL, min_value=0.0, step=0.01,
                                help=HELP['match_tol'])
    bag_tol = st.number_input('Bag-level check tolerance ($)', value=DEFAULT_BAG_TOL, min_value=0.0, step=0.01,
                              help=HELP['bag_tol'])
    inv_tol = st.number_input('Invoice-level warning tolerance ($)', value=DEFAULT_INV_TOL, min_value=0.0,
                              step=0.01, help=HELP['inv_tol'])
    st.caption(f'Defaults: match ${DEFAULT_MATCH_TOL:.2f}, bag check ${DEFAULT_BAG_TOL:.2f}, '
               f'invoice warning ${DEFAULT_INV_TOL:.2f}.')
st.write(f'In force: Match if |bags - invoice| <= **${match_tol:.2f}** | bag check **${bag_tol:.2f}** | '
         f'invoice warning **${inv_tol:.2f}**')
parquet = st.checkbox('Also save the transformed bag table as Parquet (much smaller than the ~280 MB CSV)')

if st.button('Run', type='primary'):
    settings = Settings(full_recalc=full, bag_tol=bag_tol, inv_tol=inv_tol, match_tol=match_tol)
    run_dir = new_run_dir()
    bar = st.progress(0.0, text='Starting...')
    box = st.empty()
    state = {i: 'pending' for i in range(1, len(STEPS) + 1)}
    t0 = time.time()

    def render(current):
        lines = []
        for i, name in enumerate(STEPS, 1):
            icon = ':material/check_circle:' if i < current else (
                ':material/autorenew:' if i == current else ':material/radio_button_unchecked:')
            lines.append(f'{icon} Step {i}: {name}')
        box.markdown('  \n'.join(lines))

    def progress(step, label, frac=None):
        bar.progress(min(1.0, (step - 1 + (frac or 0.0)) / len(STEPS)),
                     text=f'Step {step} of {len(STEPS)}: {label}')
        render(step)

    try:
        res = run_frames(loaded['t1'], loaded['t4'], settings, progress,
                         out_t4_csv=os.path.join(run_dir, FILES['table4_csv']))
        bar.progress(1.0, text='Saving results...')
        exporters.write_recon_csv(res.recon, os.path.join(run_dir, FILES['recon_csv']))
        exporters.write_log(os.path.join(run_dir, FILES['log']), res)
        exporters.write_excel(os.path.join(run_dir, FILES['recon_xlsx']), res)
        if parquet:
            exporters.write_parquet(res.transform.t4, os.path.join(run_dir, FILES['table4_parquet']))
        inputs = {'table1': file_fingerprint(loaded['t1_path']), 'table4': file_fingerprint(loaded['t4_path'])}
        exporters.write_metadata(os.path.join(run_dir, FILES['meta']), res, inputs,
                                 {'elapsed_seconds': round(time.time() - t0, 1)})
    except Exception as e:  # noqa: BLE001
        st.error(f'The run failed: {type(e).__name__}: {e}')
        st.caption(f'Partial output (if any) is in {run_dir}. It has no run_metadata.json, so it is shown as '
                   f'incomplete in Run history.')
        raise
    st.session_state['result'] = res
    st.session_state['run_dir'] = run_dir
    bar.progress(1.0, text=f'Done in {time.time() - t0:,.0f} s')
    render(len(STEPS) + 1)
    st.success(f'Finished. Results saved to `{run_dir}`.')
    st.page_link('pages/3_results.py', label='Open **3. Results**', icon=':material/arrow_forward:')
