# Seepsight

**Evidence-driven procurement intelligence.**

See the gaps. Show the impact. Act with confidence.

Seepsight helps organisations examine purchasing records, identify potential procurement leakage, investigate supplier performance and trace findings back to supporting evidence.

**Live applications:** [Seepsight](https://seepsight.streamlit.app/) · [Hybrid AI companion](https://seepsight-hybrid-ai.web.app/)  
**Source code:** [GitHub repository](https://github.com/damolajalal/seepsight)  
**License:** MIT

> **Demo data:** The public demonstration uses simulated procurement records. Displayed exposure figures are illustrative amounts for review, not confirmed losses or recovered savings.

## What Seepsight does

- **Connect procurement data** — upload CSV and Excel files, including multiple files with different structures.
- **Map and validate records** — map unfamiliar column names, normalise data and check whether the available fields support analysis.
- **Detect potential leakage** — identify short deliveries, price discrepancies, delayed approvals and declining supplier performance.
- **Trace findings to evidence** — inspect affected records and understand why an issue was flagged.
- **Manage investigations** — organise cases, assign actions and track follow-up.
- **Ask questions** — explore procurement information through the Ask Seepsight experience.
- **Review and report** — examine supplier performance, findings and procurement summaries.

## Application

The Streamlit application contains nine work areas:

1. Overview
2. Connect Your Data
3. Findings
4. Suppliers
5. Cases and Actions
6. Ask Seepsight
7. Reports
8. Company Profile
9. Settings

## Firebase AI Logic

The separate Hybrid AI companion uses the **Firebase AI Logic JavaScript SDK** to connect Gemini capabilities to Seepsight's procurement context.

- **Hybrid inference:** prioritises on-device Gemini Nano inference on supported desktop Chrome environments.
- **Consent-based cloud processing:** cloud inference is available only after the user explicitly consents.
- **Evidence-bounded prompts:** the companion receives relevant procurement findings and context, not unrestricted access to raw company datasets.
- **Numerical safeguards:** generated numerical claims are checked against supplied evidence; unsupported responses are retried once with stricter instructions and withheld if they still fail validation.
- **Firebase protection:** Firebase App Check is initialized with reCAPTCHA Enterprise.

The procurement engine remains responsible for detecting anomalies and calculating potential exposure. Firebase AI Logic powers the explanation and assistance layer; it does not replace the underlying analytical calculations.

See the [Firebase AI Logic implementation guide](docs/FIREBASE_AI_LOGIC.md) for architecture, setup and verification details.

## Technology

**Application and data:** Python, Streamlit, BigQuery, Firestore  
**AI:** Firebase AI Logic, Gemini, Gemini Nano, NVIDIA NIM  
**Web companion and protection:** JavaScript, Firebase Hosting, Firebase App Check, reCAPTCHA Enterprise  
**Supporting services:** Google Cloud Secret Manager

## Run the Streamlit application locally

Use Python 3.10 or later and install the project dependencies:

```bash
pip install -r requirements.txt
streamlit run app.py
```

Configure the required application secrets and cloud services for your environment before using authenticated workspaces, persistent storage or external database connections.

## Run the Hybrid AI companion locally

Requirements include Node.js 20.19 or later, a configured Firebase Web App, Firebase AI Logic enabled for the project and a reCAPTCHA Enterprise site key.

```bash
cd web-hybrid-ai
cp .env.example .env.local
# Add the Firebase Web App values and reCAPTCHA Enterprise site key.
npm install
npm test
npm run build
npm run dev
```

See the [Hybrid AI implementation guide](docs/FIREBASE_AI_LOGIC.md) for configuration and browser requirements. On-device Gemini Nano availability depends on supported desktop Chrome versions and hardware; Chrome on Android is not supported for this web on-device inference path.

## Testing

Python tests:

```bash
pytest
```

Hybrid AI companion:

```bash
cd web-hybrid-ai
npm test
npm run build
```

## Data handling

Use synthetic or appropriately anonymised records when evaluating the public demo. Do not upload credentials, bank details, personal information or confidential supplier records without first reviewing the deployment's security, access controls and data-handling arrangements.

## License

This project is licensed under the [MIT License](LICENSE). Third-party libraries and services remain subject to their respective terms and licences.


## Jira integration

The authenticated Seepsight sidebar includes a short-lived, single-use Jira account pairing-code panel. See [Jira account linking](docs/JIRA_ACCOUNT_LINKING.md) for the security model and current integration status. The Jira API and Forge app are maintained in the separate [Seepsight Intelligence for Jira repository](https://github.com/damolajalal/Seepsight-Intelligence-for-Jira).
