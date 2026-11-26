import altair as alt
import pandas as pd
import streamlit as st

from core.diagnostics import invoice_drilldown, subinvoice_diagnostic
from core.reconcile import RECON_COLUMNS
from core.runlog import KIND_LABELS
from ui_common import HELP, money, require_result, style_recon

st.title('3. Results')
res = require_result()
loaded = st.session_state.get('loaded')
t, recon, s = res.transform, res.recon, res.settings
inv_amt = pd.to_numeric(recon['Total Invoice Amount ($)'], errors='coerce')
n_match = int((recon['Match?'] == 'Match').sum())
n_mis = int((recon['Match?'] == 'Mismatch').sum())
n_unk = int(recon['Match?'].str.startswith('?').sum())

st.caption(f'Run folder: `{st.session_state.get("run_dir", "")}` | mode: '
           f'{"full recalculation" if s.full_recalc else "default"} | match tolerance ${s.match_tol:.2f}')
k = st.columns(4)
k[0].metric('Bag rows in / out', f'{t.rows_in:,} / {t.rows_out:,}',
            delta='same' if t.rows_in == t.rows_out else 'CHANGED', delta_color='off' if t.rows_in == t.rows_out else 'inverse')
k[1].metric('Multi-invoice cells before / after', f'{t.semicolon_before:,} / {t.semicolon_after:,}',
            help='Cells with several invoice IDs separated by semicolons. After must be 0.')
k[2].metric('Reconciliation rows', f'{len(recon):,}', help='One row per invoice and category.')
k[3].metric('Match / Mismatch', f'{n_match:,} / {n_mis:,}',
            help=f'Match = bags and invoice differ by no more than ${s.match_tol:.2f}. '
                 f'{n_unk} further rows are invoices not found in TABLE 1.')
k = st.columns(3)
k[0].metric('Total invoiced', money(float(inv_amt.sum())))
k[1].metric('Total allocated to bags', money(float(recon['Total Cost Allocated to Bags ($)'].sum())))
k[2].metric('Net difference (bags - invoices)', money(float(recon['Difference ($)'].sum())),
            help='Positive = more allocated to bags than invoiced.')
if t.semicolon_after:
    st.error(f'{t.semicolon_after:,} multi-invoice cell(s) remain after the transform - see the Warnings tab.')
st.caption('Not reconciled (passed through): BASE FREIGHT CHARGE ($) and FUEL SURCHARGE ($). '
           'Only the combined Inland Transportation total is reconciled.')

tab_rec, tab_iss, tab_drill, tab_chart, tab_warn = st.tabs(
    ['Reconciliation', 'Issues', 'Drill-down', 'Charts', 'Warnings'])

# ---------------------------------------------------------------- Reconciliation
with tab_rec:
    f = st.columns(4)
    cats = f[0].multiselect('Category', sorted(recon['Service Category'].unique()))
    lsps = f[1].multiselect('LSP', sorted(x for x in recon['LSP Name'].unique() if x))
    ves = f[2].multiselect('Vessel', sorted(x for x in recon['AOC Vessel Name'].unique() if x))
    stat = f[3].multiselect('Match status', sorted(recon['Match?'].unique()))
    thr = st.number_input('Only show rows with |difference| of at least ($)', min_value=0.0, value=0.0, step=1.0)
    q = st.text_input('Invoice ID contains')
    v = recon
    if cats: v = v[v['Service Category'].isin(cats)]
    if lsps: v = v[v['LSP Name'].isin(lsps)]
    if ves: v = v[v['AOC Vessel Name'].isin(ves)]
    if stat: v = v[v['Match?'].isin(stat)]
    if thr > 0: v = v[v['Difference ($)'].abs().fillna(float('inf')) >= thr]
    if q: v = v[v['Invoice ID'].str.contains(q.strip(), case=False, regex=False)]
    v = v.assign(_abs=v['Difference ($)'].abs()).sort_values('_abs', ascending=False, na_position='first') \
        .drop(columns='_abs')
    st.write(f'**{len(v):,}** of {len(recon):,} rows (largest absolute difference first; click a header to re-sort)')
    st.dataframe(style_recon(v[RECON_COLUMNS]), use_container_width=True, hide_index=True, height=520)

# ---------------------------------------------------------------- Issues
with tab_iss:
    st.write('Exceptions grouped by what they mean, so you know what to fix first.')
    for key, iss in res.issues.items():
        label = f'{iss["title"]} - {iss["count"]:,}'
        with st.expander(label, expanded=(key in ('no_bags', 'material') and iss['count'] > 0)):
            st.caption(iss['help'])
            c = st.columns(2)
            c[0].metric('Count', f'{iss["count"]:,}')
            c[1].metric(iss['impact_label'], money(iss['impact']))
            if key == 'no_bags' and iss['count']:
                e = iss['extra']
                c = st.columns(3)
                c[0].metric('Credit notes (negative amounts)', f'{e["credit_count"]:,}',
                            help='Negative invoices with no bags. These may be expected rather than a gap.')
                c[1].metric('Gross value (absolute)', money(e['gross']))
                c[2].metric('Net value', money(e['net']), help='Credits offset real unallocated costs.')
                show = st.radio('Show', ['All', 'Credit notes only', 'Excluding credit notes'], horizontal=True,
                                key='nb_filter')
                df = iss['df']
                if show == 'Credit notes only': df = df[df['Credit / negative amount']]
                if show == 'Excluding credit notes': df = df[~df['Credit / negative amount']]
                st.dataframe(style_recon(df.drop(columns=['Bags Referencing Invoice'])), use_container_width=True,
                             hide_index=True)
                diag = subinvoice_diagnostic(recon, t.t4, t.max_ids)
                if len(diag):
                    st.markdown('**Diagnostic: sub-invoice IDs (e.g. `805971/2`)**')
                    st.caption('Checks TABLE 4 directly. "Exact ID found" = False means no bag uses this exact '
                               'sub-invoice ID in any category, so it is genuinely unreferenced and not an ID-format '
                               'mismatch. Sibling sub-invoices that are used are listed for context.')
                    st.dataframe(diag, use_container_width=True, hide_index=True)
            elif iss['count']:
                df = iss['df']
                st.dataframe(style_recon(df.drop(columns=['Bags Referencing Invoice'], errors='ignore'))
                             if 'Match?' in df.columns else df, use_container_width=True, hide_index=True)

# ---------------------------------------------------------------- Drill-down
with tab_drill:
    if not loaded:
        st.info('Drill-down needs the loaded input files (not available after restarting the app).')
    else:
        c = st.columns(2)
        cat = c[0].selectbox('Category', sorted(recon['Service Category'].unique()))
        invs = recon.loc[recon['Service Category'] == cat].assign(_a=lambda d: d['Difference ($)'].abs()) \
            .sort_values('_a', ascending=False, na_position='first')
        inv = c[1].selectbox('Invoice (largest differences first)', invs['Invoice ID'].tolist(),
                             format_func=lambda i: f'{i}  ({money(invs.set_index("Invoice ID").loc[i, "Difference ($)"])})')
        if inv:
            st.dataframe(style_recon(invs[invs['Invoice ID'] == inv][RECON_COLUMNS]), use_container_width=True,
                         hide_index=True)
            d = invoice_drilldown(loaded['t4'], t.t4, t.max_ids, cat, inv)
            if d.empty:
                st.info('No bags reference this invoice in this category.')
            else:
                st.write(f'**{len(d):,} bag(s)** reference invoice {inv}. '
                         f'Recalculated total: {money(float(d["Recalculated charge for this invoice ($)"].sum()))}')
                st.dataframe(d, use_container_width=True, hide_index=True, height=420)

# ---------------------------------------------------------------- Charts
with tab_chart:
    BLUE = '#2f6fb7'
    base = recon[recon['Match?'] != '? (invoice not in TABLE1)'].copy()
    mm = base[base['Match?'] == 'Mismatch'].copy()
    st.subheader('Difference by category')
    if mm.empty:
        st.success('No mismatches.')
    else:
        g = mm.groupby('Service Category').agg(abs_diff=('Difference ($)', lambda x: x.abs().sum()),
                                               net=('Difference ($)', 'sum'), n=('Invoice ID', 'size')).reset_index()
        g = g.rename(columns={'abs_diff': 'Sum of absolute differences ($)', 'net': 'Net difference ($)',
                              'n': 'Mismatched invoices', 'Service Category': 'Category'})
        st.altair_chart(alt.Chart(g).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
            x=alt.X('Sum of absolute differences ($):Q', axis=alt.Axis(format='$,.0f')),
            y=alt.Y('Category:N', sort='-x', title=None),
            tooltip=['Category', alt.Tooltip('Sum of absolute differences ($):Q', format='$,.2f'),
                     alt.Tooltip('Net difference ($):Q', format='$,.2f'), 'Mismatched invoices']),
            use_container_width=True)
        st.caption('Mismatched invoices only. Bars show total absolute difference; hover for net (signed) difference.')

        st.subheader('Largest mismatches')
        n = st.slider('How many', 5, 50, 15)
        top = mm.assign(a=mm['Difference ($)'].abs()).nlargest(n, 'a')
        top['Label'] = top['Invoice ID'] + '  ·  ' + top['Service Category']
        st.altair_chart(alt.Chart(top).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
            x=alt.X('Difference ($):Q', axis=alt.Axis(format='$,.0f')),
            y=alt.Y('Label:N', sort=alt.EncodingSortField('a', order='descending'), title=None),
            tooltip=['Invoice ID', 'Service Category', 'LSP Name', alt.Tooltip('Difference ($):Q', format='$,.2f')]),
            use_container_width=True)
        st.caption('Negative = less allocated to bags than invoiced.')

    st.subheader('Match rate by LSP')
    lsp = base[base['LSP Name'] != ''].groupby('LSP Name').agg(
        rows=('Invoice ID', 'size'), matched=('Match?', lambda x: (x == 'Match').sum())).reset_index()
    if lsp.empty:
        st.info('No LSP names in TABLE 1.')
    else:
        min_rows = st.slider('Hide LSPs with fewer reconciliation rows than', 1, 50, 5)
        lsp = lsp[lsp['rows'] >= min_rows]
        lsp['Match rate'] = lsp['matched'] / lsp['rows']
        st.altair_chart(alt.Chart(lsp).mark_bar(color=BLUE, cornerRadiusEnd=3).encode(
            x=alt.X('Match rate:Q', axis=alt.Axis(format='%'), scale=alt.Scale(domain=[0, 1])),
            y=alt.Y('LSP Name:N', sort='-x', title=None),
            tooltip=['LSP Name', alt.Tooltip('Match rate:Q', format='.1%'), 'rows', 'matched']),
            use_container_width=True)

# ---------------------------------------------------------------- Warnings
with tab_warn:
    w = res.log.warnings_frame()
    if w.empty:
        st.success('No warnings.')
    else:
        c = st.columns(3)
        kinds = c[0].multiselect('Type', sorted(w['kind_label'].unique()))
        cat_f = c[1].multiselect('Category ', sorted(x for x in w['category'].unique() if x))
        text = c[2].text_input('Invoice / bag contains')
        if kinds: w = w[w['kind_label'].isin(kinds)]
        if cat_f: w = w[w['category'].isin(cat_f)]
        if text:
            m = w['invoice_id'].str.contains(text, case=False, regex=False) | \
                w['bag_id'].astype(str).str.contains(text, case=False, regex=False)
            w = w[m]
        st.write(f'**{len(w):,}** warning(s)')
        st.dataframe(w[['kind_label', 'category', 'invoice_id', 'bag_id', 'amount', 'message']]
                     .rename(columns={'kind_label': 'Type', 'category': 'Category', 'invoice_id': 'Invoice',
                                      'bag_id': 'Bag', 'amount': 'Amount ($)', 'message': 'Message'}),
                     use_container_width=True, hide_index=True, height=480)
