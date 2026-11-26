# Launches the Cost Allocation Reconciliation app.  Usage:  .\run.ps1
Set-Location $PSScriptRoot
if (-not (Test-Path .venv)) {
    Write-Host 'Creating virtual environment (first run only)...'
    py -3.12 -m venv .venv
    & .\.venv\Scripts\python.exe -m pip install -q -r requirements.txt
}
& .\.venv\Scripts\python.exe -m streamlit run app.py
