# Seepsight

**See the gaps. Show the impact. Act with confidence.**

Seepsight reviews a company's purchasing records (orders, deliveries, invoices and approvals), points out issues that may need
attention, shows the records behind each one, and helps the company track what happens next.

> Early preview. Demonstration companies use simulated data only. Company logins and private storage are not built yet,
> so please upload only sample or simulated records.

## What it does
- **Connect your data**: upload Excel or CSV files (one file, or several) with any column names; we match them and ask you to confirm.
- **Overview, Findings, Suppliers**: plain-language results, with the supporting records for every finding.
- **Cases and actions**: assign, add notes and track status.
- **Ask Seepsight**: questions answered from the records in the workspace.
- **Reports**: download an Excel or CSV summary.

## Run it on your computer
```
pip install -r requirements.txt
streamlit run app.py
```

## Layout
- `app.py` – navigation and page frame
- `pages/` – one file per page
- `seepsight/engine.py` – column matching, data checks, detection and the early-warning model
- `seepsight/plain.py` – the plain-English wording
- `data/demo/` – simulated demonstration results
- `data/samples/` – sample files to try the upload page

## Privacy note
Uploaded records live only in the visitor's session and are not stored. Never commit keys or real company data to this repository.
