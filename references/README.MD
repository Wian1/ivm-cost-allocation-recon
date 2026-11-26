# Cost Allocation V2: TABLE 4 Transform

This folder holds a Python script, [transform_table4.py](transform_table4.py), that cleans up the bag-level cost allocation table (TABLE 4) and checks it against the invoice table (TABLE 1).

## 1. What problem does it solve?

- **TABLE 1** (`INVOICE - COST ALLOCATION - TABLE 1.csv`) has one row per invoice, with the dollar amount per cost category and the invoice's tonnages (in **kg**).
- **TABLE 4** (`BAG - COST ALLOCATION - TABLE 4.csv`) has one row per bag. For each of 23 cost categories it has an `... INVOICE ID.` column and a matching `... CHARGE ($)` column.

Sometimes a bag was covered by **more than one invoice** for the same category. The invoice ID cell then holds several IDs separated by semicolons, e.g. `32470; 25827; 24782`. That can't be reconciled to invoices, because one charge value sits against several invoices.

The script fixes this by:

1. Splitting each semicolon cell into separate invoice IDs.
2. Putting the 1st ID in the normal column and the 2nd, 3rd, ... in new overflow columns (`..._2`, `..._3`, ...).
3. **Recalculating the charge for each invoice from TABLE 1**, so each bag gets its fair share of each invoice.
4. Producing a **reconciliation** that compares what was allocated to bags against what was invoiced.

## 2. Files

| File | Role |
|---|---|
| `transform_table4.py` | The script |
| `BAG - COST ALLOCATION - TABLE 4.csv` | **Input**: bag-level data (584,751 rows in the latest export) |
| `INVOICE - COST ALLOCATION - TABLE 1.csv` | **Input**: invoice-level data (3,309 invoices in the latest export) |
| `table4_transformed.csv` | **Output**: clean TABLE 4 with overflow columns, no semicolons |
| `reconciliation.csv` | **Output**: one row per invoice and category, bag total vs invoice total |
| `transform.log` | **Output**: log of the last run, including all warnings |
| `COST_ALLOCATION_WORKBOOK*.xlsx` | Excel workbooks that sit on top of the data (see section 7) |
| `reconciliation - Copy.csv`, `table4_transformed copy.*` | Manual backups. The script does not use them. |
| `aocvenv/` | Python virtual environment (Python 3.13, pandas 3.0, openpyxl) |

## 3. How to run it

From PowerShell in this folder:

```powershell
# 1. Activate the virtual environment
.\aocvenv\Scripts\Activate.ps1

# 2. Put the latest exports in this folder, with these exact names:
#      BAG - COST ALLOCATION - TABLE 4.csv
#      INVOICE - COST ALLOCATION - TABLE 1.csv

# 3. Run it
python transform_table4.py
```

If the venv doesn't work, any Python with `pandas` installed will do. Your Claude settings also reference `py -3.12 transform_table4.py`.

It takes a while, as TABLE 4 is large. The log is written to the console and to `transform.log`.

### Options

| Flag | Default | Meaning |
|---|---|---|
| `--table1 PATH` | `INVOICE - COST ALLOCATION - TABLE 1.csv` | Invoice CSV |
| `--table4 PATH` | `BAG - COST ALLOCATION - TABLE 4.csv` | Bag CSV |
| `--out-table4 PATH` | `table4_transformed.csv` | Transformed bag output |
| `--out-recon PATH` | `reconciliation.csv` | Reconciliation output |
| `--log PATH` | `transform.log` | Log file (overwritten each run) |
| `--full-recalc` | off | Also recalculate charges on **single-invoice** rows (see below) |

Running it twice overwrites the outputs and the log. Copy any output you want to keep first, which is probably why the "Copy" files exist.

## 4. How it works, step by step

The numbered comments in the script (Step 1 to Step 8) match this list.

1. **Load**: both CSVs are read as text and the numeric columns are converted. A warning is logged if an expected column is missing.
2. **Invoice lookup**: TABLE 1 is indexed by `INVOICE ID.` (trimmed and upper-cased). Duplicate IDs are warned about, and the last row wins.
3. **Pre-scan**: finds the most IDs in any one cell for each category, to decide how many overflow columns to add. For example, "Other WSMD" needs 7 extra column pairs because one cell holds 8 IDs.
4. **Add and order columns**: overflow charge columns go right after their parent charge column, and overflow invoice ID columns go right after their parent invoice ID column.
5. **Process each category**: for every row whose cell contains `;`, split it, look up each invoice in TABLE 1 and recalculate (see section 5). Rows with a single ID just have the ID trimmed and upper-cased, and their charge is left as it was.
6. **Check** that no semicolons remain (the log warns if any do).
7. **Write** `table4_transformed.csv`. The row count must equal the input.
8. **Reconcile**: for each category, total the bag charges per invoice (including overflow columns) and compare them with the TABLE 1 amount.

## 5. How charges are recalculated

There are two methods, set per category in `CATEGORY_CONFIG`.

**Rate x tonnage (most categories)**

```
rate          = invoice amount (TABLE 1) / sum of bag tonnage in TABLE 4 for that invoice
bag's charge  = rate x this bag's tonnage
```

The denominator is the **TABLE 4 tonnage** for the invoice, not the TABLE 1 tonnage. This makes the bag charges add up to the invoice amount exactly, even if TABLE 1 and TABLE 4 weights disagree.

Each category uses one of three tonnage columns, set in `CATEGORY_CONFIG`:

- **Mine gross** (PUDA gross excl. sample): inland transport, other inland and performance bonus.
- **Port net**: reception, assay, sampling, WSMD, insurance, TML, umpire, ocean freight, draft survey, supervision and vessel-related categories.
- **Port gross**: other logistics, FOBs and port storage.

**Per bag (truck demurrage only)**

```
bag's charge = invoice amount / number of bags that reference that invoice
```

This applies to `Demurrage (Truck)` and `Demurrage (Truck-Other)`. It is flagged with `'recalc_method': 'per_bag'`.

### Default mode vs `--full-recalc`

- **Default**: only rows that had semicolons are recalculated. Single-invoice rows keep the charge they had in TABLE 4.
- **`--full-recalc`**: every row with an invoice ID is recalculated from TABLE 1. Use it as a one-off when you suspect the existing single-invoice charges are wrong.

## 6. Reading the results

### `reconciliation.csv`

| Column | Meaning |
|---|---|
| Invoice ID, Service Category, LSP Name, AOC Vessel Name | Which invoice and category |
| Total Cost Allocated to Bags ($) | Sum of bag charges for that invoice and category |
| Total Invoice Amount ($) | Amount in TABLE 1 |
| Difference ($) | Bag total minus invoice (sign is **bags - invoice**) |
| Match? | `Match` if the absolute difference is under $0.01, otherwise `Mismatch`. `? (invoice not in TABLE1)` if the ID isn't in TABLE 1. |

Invoices that have a TABLE 1 amount but **no bags allocated** are included with a bag total of 0, so they show up as mismatches.

The last run (584,751 bag rows, 3,309 invoices) produced 2,964 rows: 2,760 `Match` and 204 `Mismatch`.

- **104 mismatches are under $1.** These are rounding differences, for example under $1 on invoices of several hundred thousand dollars. They can be ignored.
- **100 mismatches are over $1.** These are the ones to look at (see the three groups in the log section below). 85 of them have no bags allocated at all, worth $4.98M in total, almost all of it inland transport invoices.

Performance Bonus reconciles cleanly: 11 invoices, $560,514.66, all `Match`.

### `transform.log`: what to look for

| Log line | What it means |
|---|---|
| `Semicolon cells AFTER transformation: 0` | Good. Anything above 0 needs investigation. |
| `Rows in` equals `Rows out` | Good. The script must not add or drop bag rows. |
| `[VALIDATION-BAG]` | After splitting a bag's IDs, the sum of the recalculated charges differs from the bag's original charge by more than $0.10. |
| `[VALIDATION-INV]` | Bag total and invoice total differ by more than $1.00 for an invoice. |
| `invoice ... not found in TABLE1` | A bag points at an invoice ID that doesn't exist in TABLE 1. That ID's charge is skipped. |
| `zero T4 tonnage sum` | The bags on an invoice have no tonnage, so the charge is forced to 0. |
| `Duplicate INVOICE ID. values in TABLE1` | The same invoice ID appears more than once. The last row wins. |

The last run had 5,447 bag-level and 100 invoice-level validation warnings, 0 semicolon cells remaining, and the same row count in and out. The bag-level count is much higher than the invoice-level count because one invoice problem can trip many bags. The 100 invoice-level warnings fall into three groups.

- **Invoice with no bags allocated (85 of the 100)**: the bag total is $0 against the invoiced amount. Inland transport accounts for 61 of them (about $4.80M), then Other Inland Costs (8), Reception assay (11), Sampling and Weighing (1) and Umpire (1). This means no bags reference the invoice, so check TABLE 4.
- **Truck demurrage (12 of the 15 demurrage warnings have bags but a non-zero difference)**: for example invoice `32399` shows a difference of about -$6,884, and `6900001` shows +$28,500. The per-bag split divides by the number of bags referencing the invoice, so a difference usually means some bags carry the invoice in another column.
- **Sub-invoice IDs like `805971/2`**: 15 of the zero-bag warnings are invoices with a `/n` suffix (reception assay, other WSMD and similar). The sub-invoice IDs probably aren't in TABLE 4 under that exact format.

I haven't investigated these, so treat the explanations as leads rather than conclusions.

## 7. The Excel workbooks

`COST_ALLOCATION_WORKBOOK.xlsx` (the latest) is a Power Query workbook. Its sheets are `BAG - COST ALLOCATION`, `INVOICE - COST ALLOCATION`, `SUMMARY (2)`, a hidden `BAG_UNPIVOTED (2)`, and `PQ - SETUP INSTRUCTIONS`. It has an Excel-side reconciliation of the same data. The older dated workbooks (`_20260325`, `_20260326`) are earlier versions.

Its instructions sheet describes a method that **does not split semicolon IDs or recalculate charges**. It splits the cell and attributes the **full** charge to each invoice. That is why `SUMMARY (2)` shows rows like `125428FINV; 126481FINV` with "No Invoice Data". This script replaces that approach.

I haven't checked whether the workbook is currently pointed at `table4_transformed.csv`. If you want the corrected data in Excel, point the BAG query at `table4_transformed.csv`. Because that file has extra overflow columns, the unpivot step has to include them, so check the column list in `BAG_UNPIVOTED`.

## 8. Maintenance: things to know

- **Column names must match exactly.** `CATEGORY_CONFIG` has deliberately preserved quirks from the source files:
  - `PORT WHS STORAGE INVOICE ID` has no trailing period.
  - `DRAFT SURVERY CHARGE ($)` is misspelled in TABLE 4.
  - `OTHER LOGISTICS (EX. INLAND)  ($)` has two spaces in TABLE 1.

  If the source headers change, the script logs a "missing column" warning and skips that category.
- **Adding a category**: add a dict to `CATEGORY_CONFIG` with the invoice ID column, charge column, TABLE 1 charge column, tonnage columns and divisor, and add the TABLE 1 column to `T1_CHARGE_COLS`.
- **Units**: TABLE 1 tonnage is in kg and TABLE 4 is in tons. The `t1_ton_div: 1000` setting handles the conversion where TABLE 1 weights are used.
- **Inland base and fuel**: `BASE FREIGHT CHARGE ($)` and `FUEL SURCHARGE ($)` columns are passed through unchanged. Only the combined `TOTAL INLAND` column is recalculated.
- **Performance Bonus** was added as the 23rd category. Its TABLE 4 invoice ID column is `PERFORMANCE BONUS INVOICE ID` (no trailing period) and both tables use `PERFORMANCE BONUS CHARGE ($)`. It is allocated by mine gross tonnage, which matches how the existing bag charges behave (about $15 per ton). In the current data it has no semicolon IDs, so the transform leaves its charges as they were, and it appears in the reconciliation only.
- **Re-running when the outputs are open**: the script fails with `PermissionError` if `reconciliation.csv` or `table4_transformed.csv` is open in Excel or an editor. Close them first, or write to other names with `--out-recon` and `--out-table4`.
- **Tolerances**: bag check $0.10, invoice check $1.00, `Match` under $0.01. They are hard-coded in Step 5 and Step 8.
