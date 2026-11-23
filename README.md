# Seepsight

**See the gaps. Show the impact. Act with confidence.**

Seepsight reviews a company's purchasing records (orders, deliveries, invoices and approvals), points out issues that may need attention, shows the records behind each one, and helps the company track what happens next.

> Early preview. Demonstration companies use simulated data only. Use sample or simulated records until your deployment has passed its cloud and security checks.

## What it does
- **Connect your data**: upload Excel or CSV files (one file, or several) with any column names; we match them and ask you to confirm.
- **Overview, Findings, Suppliers**: plain-language results, supporting records, detector-readiness states and a transparent supplier scorecard.
- **Cases and actions**: assign, add notes and track status.
- **Ask Seepsight**: questions answered from the records in the workspace.
- **Reports**: download an Excel or CSV summary.

## Run the Streamlit application
```bash
pip install -r requirements.txt
streamlit run app.py
```

## Phase 7 — Firebase AI Logic Hybrid Web/Chrome companion

The `web-hybrid-ai/` directory contains a separate browser companion. It uses Firebase AI Logic, prefers Chrome on-device inference, and offers cloud fallback only when the user explicitly consents for that request. It does not replace the Streamlit application or its deterministic procurement engine.

See [the Phase 7 implementation notes](docs/PHASE7_BUILDHYBRIDAI.md) and [the Web app setup guide](web-hybrid-ai/README.md). Configure the Firebase Web App and reCAPTCHA Enterprise values in `web-hybrid-ai/.env.local`; never commit that file or a debug token. Set `SEEPSIGHT_HYBRID_AI_URL` in the Streamlit environment to show a link from Ask Seepsight.

## Privacy and deployment

AI explains verified findings; the deterministic procurement engine remains the source of procurement calculations. Do not submit confidential supplier records, personal information, bank details, credentials, or complete raw datasets to the companion. A successful source build does not prove live Firebase configuration, App Check enforcement, or on-device/cloud inference.
