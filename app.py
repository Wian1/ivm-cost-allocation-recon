"""Cost Allocation Reconciliation - Streamlit entry point.

Run with:  streamlit run app.py
"""
import streamlit as st

st.set_page_config(page_title='Cost Allocation Reconciliation', page_icon=':material/fact_check:',
                   layout='wide')

pages = [
    st.Page('pages/1_upload.py', title='1. Upload & check', icon=':material/upload_file:', default=True),
    st.Page('pages/2_run.py', title='2. Run', icon=':material/play_arrow:'),
    st.Page('pages/3_results.py', title='3. Results', icon=':material/dashboard:'),
    st.Page('pages/4_export.py', title='4. Export', icon=':material/download:'),
    st.Page('pages/5_history.py', title='5. Run history', icon=':material/history:'),
]
st.navigation(pages).run()
