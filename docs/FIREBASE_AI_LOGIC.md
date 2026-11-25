# Firebase AI Logic Hybrid Companion

## Overview

Seepsight includes a separate browser-based Hybrid AI companion built with the Firebase AI Logic JavaScript SDK and Google's Gemini models. It complements the Streamlit procurement application; it does not replace the deterministic procurement analysis engine.

- **Main application:** https://seepsight.streamlit.app/
- **Hybrid AI companion:** https://seepsight-hybrid-ai.web.app/

## Architecture

The companion is implemented in `web-hybrid-ai/`.

- `src/firebase.js` initializes Firebase, App Check and Firebase AI Logic model configurations.
- `src/main.js` handles user interaction, inference selection, consent and response validation.
- `src/prompt.js` builds bounded prompts from the procurement context supplied to the companion.

Firebase AI Logic is accessed through the Firebase JavaScript SDK, including `getAI()`, `GoogleAIBackend` and `getGenerativeModel()`.

## Hybrid inference and consent

The companion supports two inference paths:

1. **On-device:** Uses the on-device inference mode and prioritises Gemini Nano on supported desktop Chrome environments.
2. **Cloud:** A separate cloud model path is used only after the user explicitly consents to cloud processing.

When cloud fallback has not been approved, the companion is configured for on-device inference only. It checks the SDK-reported inference source and does not present an answer as on-device or cloud-generated when the route cannot be verified.

On-device availability depends on the supported Chrome version, operating system, hardware and model availability. Chrome on Android is not supported for this web on-device inference path.

## Evidence and response safeguards

- The companion receives bounded procurement findings and relevant context, not unrestricted access to the company's raw datasets.
- The procurement engine remains responsible for detection logic and financial calculations.
- Numerical claims in generated responses are checked against the supplied evidence.
- If a response contains unsupported numerical claims, the application attempts one stricter retry.
- Responses that still fail validation are withheld rather than presented as verified facts.

These safeguards reduce unsupported claims; they do not replace human review of procurement decisions.

## Firebase protection

Firebase App Check is initialized with a reCAPTCHA Enterprise provider. Configure the correct Firebase Web App settings and reCAPTCHA Enterprise site key for the deployment domain. Never commit production secrets, local environment files or App Check debug tokens.

## Run locally

Requirements:
- Node.js 20.19 or later.
- A configured Firebase Web App.
- Firebase AI Logic enabled for the project.
- A reCAPTCHA Enterprise site key for the local/deployed domain.

```bash
cd web-hybrid-ai
cp .env.example .env.local
# Add the Firebase Web App values and reCAPTCHA Enterprise site key.
npm install
npm test
npm run build
npm run dev
```

For local App Check debugging, follow the Firebase debug-token procedure documented in the environment setup. Do not enable debug mode or use debug tokens in production.

## Verification

The Firebase AI Logic integration, on-device inference path, explicitly consented cloud path, evidence safeguards and response-validation workflow have been tested for the current project version.

For a new deployment or material code change, repeat the automated tests and verify both inference routes on the actual target browser and domain. Confirm App Check registration/enforcement in the Firebase Console for that deployment. A successful local build alone is not proof of live inference or App Check enforcement.

## Data handling

Use synthetic or appropriately anonymised procurement evidence when testing. Do not submit credentials, bank details, personal information or confidential supplier records unless the deployment's data-handling and security arrangements have been reviewed and approved.
