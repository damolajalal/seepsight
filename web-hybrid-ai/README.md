# Seepsight Hybrid AI — Web / Chrome

This is an additive companion to the existing Streamlit application. It does not replace the nine-page workspace or its Python procurement engine.

## Requirements
- Node.js 20.19+.
- Firebase Web App in project `seepsight-hybrid-ai`.
- Firebase AI Logic enabled.
- App Check configured with a reCAPTCHA Enterprise site key for the exact hosting domain.
- Desktop Chrome 139+ with the Prompt API and on-device model available for local inference.

## Configure and run
Copy `.env.example` to `.env.local`, then fill in the Firebase Web App values and the production reCAPTCHA Enterprise site key. For local development only, set `VITE_FIREBASE_APPCHECK_DEBUG=true`, start the app, and safelist the generated debug token in Firebase Console. Never commit a debug token or enable debug mode in production.

```bash
npm install
npm test
npm run build
npm run dev
```

## Inference and privacy
Without request-level consent, the app uses `ONLY_ON_DEVICE`. When the user consents to cloud fallback, it uses `PREFER_ON_DEVICE`; the prompt may be sent to Google's cloud model if local inference is unavailable. The interface displays the SDK-reported `inferenceSource`. Use anonymised or synthetic evidence and do not paste confidential records, personal data, bank details or credentials.

## Live verification still required
A successful source test/build does not prove live App Check attestation or either inference route. Verify App Check enforcement in Firebase Console, then test and record both `ON_DEVICE` and consented `IN_CLOUD` responses in the target Chrome environment. Confirm the actual Chrome model/version meets the challenge requirement before claiming it does.
