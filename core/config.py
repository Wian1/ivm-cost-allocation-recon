"""Category configuration, column groups and tolerances.

Copied verbatim from references/transform_table4.py. Column names carry
deliberate source quirks (do not "fix" them):
  - 'PORT WHS STORAGE INVOICE ID'  has no trailing period
  - 'DRAFT SURVERY CHARGE ($)'     is misspelled in TABLE 4
  - 'OTHER LOGISTICS (EX. INLAND)  ($)' has two spaces in TABLE 1
"""
# ---------------------------------------------------------------------------
# Tonnage denominator column names
# ---------------------------------------------------------------------------
MINE_GROSS_T1 = 'DRC DATA - PUDA GROSS WT EXCL. SAMPLE (KG)'
PORT_GROSS_T1 = 'PORT WHS GROSS WEIGHT (KG)'
PORT_NET_T1   = 'PORT WHS NET WEIGHT (KG)'

MINE_GROSS_T4 = 'PUDA GROSS WT EXCL. SAMPLE (TONS)'
PORT_GROSS_T4 = 'PORT WAREHOUSE GROSS WEIGHT (TONS)'
PORT_NET_T4   = 'PORT WAREHOUSE NET WEIGHT (TONS)'

# ---------------------------------------------------------------------------
# Category configuration — 23 invoice ID / charge column pairs (TABLE4 order)
# ---------------------------------------------------------------------------
# t1_ton_div: all TABLE1 tonnage columns are in KG; divide by 1000 to get tonnes
# t1_ton_div      → all TABLE1 tonnage columns are in KG; divide by 1000

CATEGORY_CONFIG = [
    {
        'label':         'Inland Transportation (Total)',
        'display_label': 'Inland Transportation (Total)',
        'inv_id_col': 'INLAND TRANSPORTATION INVOICE ID.',
        'charge_col': 'TOTAL INLAND (BASE & FUEL CHARGE) ($)',
        't1_charge':  'TOTAL INLAND (BASE & FUEL) ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Other Inland Transport',
        'display_label': 'Other Inland Costs',
        'inv_id_col': 'OTHER INLAND TRANSPORT INVOICE ID.',
        'charge_col': 'OTHER INLAND TRANSPORT CHARGE ($)',
        't1_charge':  'OTHER INLAND TRANSPORT ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Performance Bonus',
        'display_label': 'Performance Bonus',
        'inv_id_col': 'PERFORMANCE BONUS INVOICE ID',   # NOTE: no trailing period
        'charge_col': 'PERFORMANCE BONUS CHARGE ($)',
        't1_charge':  'PERFORMANCE BONUS CHARGE ($)',
        't1_tonnage': MINE_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': MINE_GROSS_T4,
    },
    {
        'label':         'Demurrage (Truck)',
        'display_label': 'Demurrage (Truck)',
        'inv_id_col':    'DEMURRAGE TRUCK INVOICE ID.',
        'charge_col':    'DEMURRAGE TRUCK CHARGE ($)',
        't1_charge':     'DEMURRAGE TRUCK ($)',
        't1_tonnage':    MINE_GROSS_T1,
        't1_ton_div':    1000,
        't4_tonnage':    MINE_GROSS_T4,
        'recalc_method': 'per_bag',
    },
    {
        'label':         'Demurrage (Truck-Other)',
        'display_label': 'Demurrage (Truck - Other)',
        'inv_id_col':    'DEMURRAGE OTHER INVOICE ID.',
        'charge_col':    'DEMURRAGE TRUCK OTHER CHARGE ($)',
        't1_charge':     'DEMURRAGE TRUCK OTHER ($)',
        't1_tonnage':    MINE_GROSS_T1,
        't1_ton_div':    1000,
        't4_tonnage':    MINE_GROSS_T4,
        'recalc_method': 'per_bag',
    },
    {
        'label':         'Reception Logistics',
        'display_label': 'Logistics Reception Costs',
        'inv_id_col': 'RECEPTION LOGISTICS INVOICE ID.',
        'charge_col': 'RECEPTION LOGISTICS CHARGE ($)',
        't1_charge':  'RECEPTION LOGISTICS ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Assay - Reception Related',
        'display_label': 'Assay / Environmental / Courier - On Reception',
        'inv_id_col': 'ASSAY - RECEPTION RELATED INVOICE ID.',
        'charge_col': 'ASSAY RECEPTION RELATED CHARGE ($)',
        't1_charge':  'ASSAY - RECEPTION RELATED ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Sampling & Weighing',
        'display_label': 'Sampling and Weighing',
        'inv_id_col': 'WSMD (RECEPTION) INVOICE ID.',
        'charge_col': 'WSMD (RECEPTION) ($)',
        't1_charge':  'SAMPLING WEIGHING ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Other WSMD',
        'display_label': 'Other WSMD Costs',
        'inv_id_col': 'OTHER WSMD INVOICE ID.',
        'charge_col': 'OTHER WSMD CHARGE ($)',
        't1_charge':  'OTHER WSMD ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Insurance DAP',
        'display_label': 'Insurance - DAP',
        'inv_id_col': 'INSURANCE DAP INVOICE ID.',
        'charge_col': 'INSURANCE DAP CHARGE ($)',
        't1_charge':  'INSURANCE DAP ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Insurance CIF',
        'display_label': 'Insurance - CIF',
        'inv_id_col': 'INSURANCE CIF INVOICE ID.',
        'charge_col': 'INSURANCE CIF CHARGE ($)',
        't1_charge':  'INSURANCE CIF ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Other Logistics (excl. Inland)',
        'display_label': 'Other Logistics Costs (excl. Inland)',
        'inv_id_col': 'OTHER LOGISTICS (EX. INLAND) INVOICE ID.',
        'charge_col': 'OTHER LOGISTICS (EX. INLAND) CHARGE ($)',
        't1_charge':  'OTHER LOGISTICS (EX. INLAND)  ($)',   # NOTE: two spaces before ($)
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'TML',
        'display_label': 'TML',
        'inv_id_col': 'TML INVOICE ID.',
        'charge_col': 'TML CHARGE ($)',
        't1_charge':  'TML ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Umpire Costs',
        'display_label': 'Umpire Costs',
        'inv_id_col': 'UMPIRE COST INVOICE ID.',
        'charge_col': 'UMPIRE CHARGE ($)',
        't1_charge':  'UMPIRE ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Ocean Freight',
        'display_label': 'Ocean Freight',
        'inv_id_col': 'OCEAN FREIGHT INVOICE ID.',
        'charge_col': 'OCEAN FREIGHT CHARGE ($)',
        't1_charge':  'OCEAN FREIGHT ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Dispatch',
        'display_label': 'Despatch (Vessel)',
        'inv_id_col': 'VESSEL DISPATCH INVOICE ID.',
        'charge_col': 'VESSEL DISPATCH CHARGE ($)',
        't1_charge':  'VESSEL DISPATCH ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Demurrage',
        'display_label': 'Demurrage (Vessel)',
        'inv_id_col': 'VESSEL DEMURRAGE INVOICE ID.',
        'charge_col': 'VESSEL DEMURRAGE CHARGE ($)',
        't1_charge':  'VESSEL DEMURRAGE ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         "FOB's",
        'display_label': "FOB's (incl. Overtime if incurred)",
        'inv_id_col': 'FOBs INVOICE ID.',
        'charge_col': 'FOBs CHARGE ($)',
        't1_charge':  'FOBs ($)',
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'Port WHS Storage',
        'display_label': 'Port Warehouse Storage',
        'inv_id_col': 'PORT WHS STORAGE INVOICE ID',   # NOTE: no trailing period
        'charge_col': 'PORT WHS STORAGE CHARGE ($)',
        't1_charge':  'PORT WHS STORAGE ($)',
        't1_tonnage': PORT_GROSS_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_GROSS_T4,
    },
    {
        'label':         'Draft Survey',
        'display_label': 'Draft Survey',
        'inv_id_col': 'DRAFT SURVEY INVOICE ID.',
        'charge_col': 'DRAFT SURVERY CHARGE ($)',      # NOTE: typo in source — preserved
        't1_charge':  'DRAFT SURVEY ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Load Supervision',
        'display_label': 'Vessel Load Supervision',
        'inv_id_col': 'VESSEL LOAD SUPERVISION INVOICE ID.',
        'charge_col': 'VESSEL LOAD SUPERVISION CHARGE ($)',
        't1_charge':  'VESSEL LOAD SUPERVISION ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Vessel Discharge Supervision',
        'display_label': 'Vessel Discharge Supervision',
        'inv_id_col': 'VESSEL DISCHARGE SUPERVISION INVOICE ID.',
        'charge_col': 'VESSEL DISCHARGE SUPERVISION CHARGE ($)',
        't1_charge':  'VESSEL DISCHARGE SUPERVISION ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
    {
        'label':         'Assay - Vessel Related',
        'display_label': 'Assay / Environmental / Courier - Vessel Related',
        'inv_id_col': 'ASSAY - VESSEL RELATED INVOICE ID.',
        'charge_col': 'ASSAY VESSEL RELATED CHARGE ($)',
        't1_charge':  'ASSAY - VESSEL RELATED ($)',
        't1_tonnage': PORT_NET_T1,
        't1_ton_div': 1000,
        't4_tonnage': PORT_NET_T4,
    },
]

# ---------------------------------------------------------------------------
# TABLE1 columns that need numeric conversion
# ---------------------------------------------------------------------------
T1_CHARGE_COLS = [
    'BASE FREIGHT CHARGE ($)',
    'FUEL SURCHARGE CHARGE ($)',
    'OTHER INLAND TRANSPORT ($)',
    'PERFORMANCE BONUS CHARGE ($)',
    'DEMURRAGE TRUCK ($)',
    'DEMURRAGE TRUCK OTHER ($)',
    'RECEPTION LOGISTICS ($)',
    'ASSAY - RECEPTION RELATED ($)',
    'SAMPLING WEIGHING ($)',
    'OTHER WSMD ($)',
    'INSURANCE DAP ($)',
    'INSURANCE CIF ($)',
    'OTHER LOGISTICS (EX. INLAND)  ($)',   # two spaces
    'TML ($)',
    'UMPIRE ($)',
    'OCEAN FREIGHT ($)',
    'VESSEL DISPATCH ($)',
    'VESSEL DEMURRAGE ($)',
    'FOBs ($)',
    'PORT WHS STORAGE ($)',
    'DRAFT SURVEY ($)',
    'VESSEL LOAD SUPERVISION ($)',
    'VESSEL DISCHARGE SUPERVISION ($)',
    'ASSAY - VESSEL RELATED ($)',
    'TOTAL INLAND (BASE & FUEL) ($)',
    'INVOICE AMOUNT.2',
]

T1_WEIGHT_COLS = [
    'DRC DATA - PUDA GROSS WT EXCL. SAMPLE (KG)',
    'PORT WHS GROSS WEIGHT (KG)',
    'PORT WHS NET WEIGHT (KG)',
]

T4_WEIGHT_COLS = [
    'PUDA GROSS WT EXCL. SAMPLE (TONS)',
    'PORT WAREHOUSE GROSS WEIGHT (TONS)',
    'PORT WAREHOUSE NET WEIGHT (TONS)',
]

# ---------------------------------------------------------------------------
# Tolerances (named constants; overridable at run time in the UI)
# ---------------------------------------------------------------------------
DEFAULT_BAG_TOL = 0.10     # bag-level validation: recalculated sum vs original charge ($)
DEFAULT_INV_TOL = 1.00     # invoice-level validation warning threshold ($)
# Match / Mismatch threshold. The original script used 0.01. Changed to 1.00 at
# the user's request: Mismatch only if difference < -1.00 or > +1.00.
DEFAULT_MATCH_TOL = 1.00
EXACT_TOL = 0.01           # difference at/under this is considered an exact match
                           # (used only to flag "matched within tolerance, not exact")

# Columns passed through unchanged and not reconciled (shown as "Not reconciled")
PASS_THROUGH_T4 = ['BASE FREIGHT CHARGE ($)', 'FUEL SURCHARGE ($)']   # TABLE 4 names

T1_ID_COL = 'INVOICE ID.'
T4_BAG_COL = 'BAG ID'
T1_LSP_COL = 'LSP NAME'
T1_VESSEL_COL = 'AOC VESSEL NAME'
