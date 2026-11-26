# Prompt: Build the Cost Allocation Reconciliation Streamlit App

> Before pasting this into Claude Code in the new folder, copy these into that folder (e.g. under `reference/`):
> - `transform_table4.py` (the working script, treat it as the source of truth for the logic)
> - `README.md` (explains the logic)
> - A **small sample** of each input CSV (first ~500 rows of `BAG - COST ALLOCATION - TABLE 4.csv` and the full `INVOICE - COST ALLOCATION - TABLE 1.csv`) plus the current `reconciliation.csv`, for testing and regression checks.
>
> Do not copy the 250 MB bag CSV unless you want it for performance testing.

---

## PROMPT (paste from here)

You are building a Streamlit application that formalises an existing command-line workflow. The workflow is implemented in `reference/transform_table4.py` and documented in `reference/README.md`. Read both fully before writing any code.

### 1. Context and goal

A mining export supply chain allocates logistics invoice costs down to individual bags of concentrate.

- **TABLE 1 (invoice level)**: one row per invoice. Holds the dollar amount per cost category (23 categories) and invoice-level weights in **kg**. Key: `INVOICE ID.`
- **TABLE 4 (bag level)**: one row per bag. For each of 23 categories it has an `... INVOICE ID.` column and a matching `... CHARGE ($)` column. Weights are in **tons**.

Problem: a bag can be covered by several invoices for one category, giving cells like `32470; 25827; 24782`, so one charge sits against several invoices and cannot be reconciled.

The existing script fixes this by splitting the IDs into overflow columns (`_2`, `_3`, ...), recalculating each bag's charge per invoice from TABLE 1, and producing a reconciliation of bag-allocated totals vs invoice totals.

Goal: replace "run a script, then open CSVs and logs by hand" with a guided Streamlit app that a non-developer finance/ops analyst can use on their own, with the reconciliation results explorable and exportable.

### 2. Non-negotiable: preserve the calculation logic

Move the logic from `transform_table4.py` into an importable, UI-free module (e.g. `core/`), and have the app call it. **Do not change the numbers.** Specifically preserve:

- The `CATEGORY_CONFIG` list (23 categories) with its exact column names, including the deliberate source quirks: `PORT WHS STORAGE INVOICE ID` (no trailing period), `DRAFT SURVERY CHARGE ($)` (typo), `OTHER LOGISTICS (EX. INLAND)  ($)` (two spaces in TABLE 1).
- ID cleaning: trim, upper-case, treat `nan`/empty as no ID. Split on `;`.
- Overflow columns: the pre-scan finds the max IDs per cell per category; overflow charge columns go directly after their parent charge column, overflow ID columns directly after their parent ID column.
- Two recalculation methods:
  - **Rate x tonnage**: `rate = invoice amount (T1) / sum of TABLE 4 tonnage of all bags referencing that invoice`; `bag charge = rate x bag tonnage`. The denominator is the TABLE 4 tonnage, not the TABLE 1 tonnage. Tonnage column per category is one of mine gross, port net or port gross, as set in the config.
  - **Per bag** (`Demurrage (Truck)` and `Demurrage (Truck-Other)` only): `invoice amount / number of bags referencing that invoice`.
- Default mode only recalculates rows containing `;`. Single-invoice rows keep their original charge. An optional **full recalc** mode recalculates every row with an invoice ID.
- Duplicate invoice IDs in TABLE 1: warn, last row wins.
- Invoice ID not in TABLE 1: warn and skip that ID. Zero TABLE 4 tonnage on an invoice: charge forced to 0 and warn.
- Reconciliation: per category and invoice, sum bag charges across primary and overflow columns, compare with TABLE 1. Include TABLE 1 invoices that have a non-zero amount but no bags (bag total 0). `Match` if `abs(diff) < 0.01`, else `Mismatch`; `? (invoice not in TABLE1)` if the invoice is absent from TABLE 1. Difference sign is bags minus invoice. Output columns: Invoice ID, Service Category (display label), LSP Name, AOC Vessel Name, Total Cost Allocated to Bags ($), Total Invoice Amount ($), Difference ($), Match?.
- Validations: bag-level (recalculated sum vs original charge, tolerance $0.10), invoice-level (tolerance $1.00), no semicolons remaining, row count in = row count out.

Tolerances ($0.10, $1.00, $0.01) should become named constants, shown in the UI and overridable in an "Advanced" expander.

**Regression requirement**: write a test that runs the new core module on the sample inputs and asserts the output is identical (within 1e-6) to the output of the original script on the same inputs. Run the original script to generate the golden files. Do this before building the UI.

### 3. Known gaps to handle (please verify against the data, don't assume)

I noticed these while reading the existing script and data. Check each, and raise anything that affects the numbers rather than silently fixing it:

1. **Performance bonus is now in the config (resolved).** It is the 23rd category: invoice ID column `PERFORMANCE BONUS INVOICE ID`, charge column `PERFORMANCE BONUS CHARGE ($)` in both tables, allocated by mine gross tonnage. It has no semicolon IDs today and reconciles cleanly (11 invoices, $560,514.66). `BASE FREIGHT` and `FUEL SURCHARGE` stay pass-through and are not reconciled; show them in the UI as "Not reconciled".
2. **`skip_recalc` and `if cfg['t1_charge'] is None` branches are dead code** (no config uses them). Remove or keep as an explicit, tested feature.
3. **Reference numbers (latest run, for regression checks only).** 584,751 bag rows, 3,309 invoices, 157,274 semicolon cells before and 0 after, 2,964 reconciliation rows (2,760 Match, 204 Mismatch, of which 100 are over $1), 5,447 bag-level and 100 invoice-level validation warnings. Compute everything live in the app, never hard-code these.
4. **Sub-invoice IDs** like `805971/2` show bags $0 in the reconciliation. This is probably an ID-format mismatch between TABLE 1 (`NO. OF SUB-INVOICES` column exists) and TABLE 4. Investigate it, and if confirmed, expose it as a diagnostic in the app rather than guessing a fix.
5. **Row-iteration performance.** The semicolon rows are processed with `iterrows`/`.at` loops, and the pre-scan loops in Python. With ~585k rows and ~157k semicolon cells this is slow. Optimise (vectorised `str.split(expand=True)`, grouped sums, merges) but only after the regression test passes, and keep the output identical.

### 4. App requirements

**Stack**: Python 3.12+, Streamlit, pandas (consider Polars or PyArrow for loading the large file if it gives a real speed-up, but keep outputs identical), openpyxl/xlsxwriter for Excel export. Use `st.cache_data` / `st.cache_resource` sensibly, and `st.session_state` for run state. Provide `requirements.txt`, a `README.md` with run instructions for Windows PowerShell, and a `run.bat`/`run.ps1` launcher.

**Pages / flow** (use `st.navigation` multipage or a clear stepper):

1. **Upload and validate**
   - Upload TABLE 1 and TABLE 4 CSVs (support large files; also allow selecting a file path from a configured local folder, since a 250 MB upload through the browser is clumsy).
   - Immediate schema check: list expected columns per category and show which are missing, with the exact-name quirks called out. Block the run if a required column is missing, and say which category would be skipped.
   - Show quick profile: row counts, number of unique invoices, number of semicolon cells per category, max IDs per cell (i.e. overflow columns that will be added), duplicate TABLE 1 invoice IDs, bags with missing weights.
2. **Run settings**
   - Mode: default (semicolon rows only) vs full recalc, with a plain-language explanation of the difference and a warning that full recalc overwrites existing single-invoice charges.
   - Tolerances (advanced).
   - A "Run" button with a progress bar and live status per step (the 8 steps in the script).
3. **Results dashboard**
   - Headline KPIs: rows in/out, semicolon cells before/after (must be 0), reconciliation rows, Match count, Mismatch count, total $ invoiced vs total $ allocated, net difference.
   - Reconciliation table: filterable by category, LSP, vessel, match status, and an absolute-difference threshold. Sortable. Default sort: largest absolute difference first. Colour-code Mismatch.
   - A categorised **issues panel** that classifies exceptions instead of just listing them: (a) invoice with no bags allocated, (b) invoice not in TABLE 1, (c) rounding-level difference (< $1), (d) material difference (>= $1), (e) zero-tonnage invoice, (f) bag-level validation failures. Each shows count, total $ impact and a drill-down table.
   - Drill-down: select an invoice and see the bags that reference it, their tonnage, original vs recalculated charge, and the other invoices on the same bags.
   - A charts tab: difference by category, top N mismatches, match rate by LSP. Keep charts simple and readable.
4. **Export**
   - Download the transformed TABLE 4 (CSV, and optionally Parquet because it is ~280 MB as CSV), the reconciliation (CSV and a formatted Excel workbook with the issues panel as separate sheets), and the log.
   - Write outputs into a timestamped run folder (`runs/YYYYMMDD_HHMMSS/`) alongside a small `run_metadata.json` (input file names, sizes, hashes, row counts, mode, tolerances, summary counts) so a run can be audited and reproduced. This replaces the manual "copy the old files before re-running" habit.
5. **Run history** (optional but wanted): list previous runs from `runs/`, open one, and **compare two runs** (which invoice/category pairs changed Match status or difference).

**UX rules**
- Plain-language labels aimed at finance/ops users; no jargon like "overflow columns" without a tooltip.
- Every warning in the old log should appear in the UI in a structured, filterable form, as well as in the downloadable log.
- Never block the UI thread silently: show progress for long steps, and make the run resumable/cached where it is safe.
- Fail loudly with a clear message when inputs are malformed (wrong delimiter, encoding/BOM, empty file).
- Handle memory: the bag file is ~250 MB. Load with explicit dtypes where possible, drop unneeded columns early in the reconciliation path, and note the memory needed.

### 5. Suggested structure

```
app.py                      # Streamlit entry / navigation
pages/
core/
  config.py                 # CATEGORY_CONFIG, tolerances, column groups
  loaders.py                # read + validate + type-convert CSVs
  transform.py              # split IDs, overflow columns, recalc (UI-free)
  reconcile.py              # reconciliation + issue classification
  exporters.py              # CSV / Parquet / Excel / log
  runs.py                   # run folders, metadata, history, comparison
tests/
  test_regression.py        # new core vs original script on sample data
  test_transform.py         # unit tests: split, per_bag, rate x tonnage, edge cases
reference/                  # original script, README, sample data (read-only)
runs/                       # generated, gitignored
```

### 6. Process I want you to follow

1. Read the reference script and README. Then **summarise your understanding back to me in under 20 lines and list any questions** (especially item 4 of section 3) before writing code.
2. Create the core module and the regression test first. Show me the regression test passing.
3. Then build the UI page by page, running the app and checking each page works on the sample data before moving on.
4. Add unit tests for the edge cases: single ID, many IDs, duplicate IDs in one cell, trailing semicolons, whitespace/case differences, invoice missing from TABLE 1, zero tonnage, per-bag categories, and TABLE 1 invoices with no bags.
5. Finish with a short README, and a list of anything you were unsure about or changed.

Do not add features beyond this brief without asking. Do not change the calculation results without telling me first and explaining why.

## END OF PROMPT
