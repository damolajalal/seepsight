# Phase 7 — Firebase AI Logic Hybrid Web Integration

Phase 7 adds `web-hybrid-ai/` as the Firebase AI Logic Web/Chrome experience embedded inside the existing authenticated Seepsight workspace. The existing Streamlit application, nine pages, Python procurement engine and earlier AI integrations remain in place. Findings and Ask Seepsight can hand a bounded, deterministic summary to the embedded companion; the companion never receives the full source dataset or Streamlit/Firebase Admin credentials.

## Implemented
- Firebase JavaScript SDK and Firebase AI Logic imports.
- Request-level consent: `ONLY_ON_DEVICE` by default; `PREFER_ON_DEVICE` only when cloud fallback is explicitly approved.
- Device-model initialization before inference and display of the SDK-reported `inferenceSource`.
- Firebase App Check initialization with reCAPTCHA Enterprise and local debug-token guidance.
- Evidence-bounded prompts and a numeric consistency guardrail. The deterministic procurement engine remains the source of procurement facts.

## Verify before calling Phase 7 live
1. Run `npm install`, `npm test` and `npm run build` in `web-hybrid-ai/`.
2. Configure the Firebase Web App environment values and the reCAPTCHA Enterprise key for the exact hosting domain.
3. Confirm App Check is enforced for Firebase AI Logic.
4. Deploy the Vite `dist/` output to Firebase Hosting and verify the public URL.
5. Test a real `ON_DEVICE` response in supported desktop Chrome and a consented `IN_CLOUD` response. Record the actual Chrome model/version; source code alone cannot prove the required Gemini Nano version.

This code integration does not by itself configure Firebase Console, create App Check attestation, deploy Hosting, or prove live inference.


## Streamlit workspace integration
- Set `SEEPSIGHT_HYBRID_AI_URL` in the Streamlit app's environment or secrets to the deployed HTTPS Firebase Hosting URL.
- The Findings page passes only the selected finding's deterministic `plain.what_we_found` summary.
- Ask Seepsight passes only the latest deterministic answer and its question, not the full chat history or source tables.
- Context is transferred through a versioned `postMessage` payload. The companion accepts messages only from its immediate parent and enforces field-length limits.
- The parent frame targets the configured HTTPS origin. Firebase Hosting's `frame-ancestors` policy permits only the Seepsight production and development Streamlit domains.
- The user must still review the supplied context and explicitly choose cloud fallback for each request. No cloud consent is inferred from the embedding.
- The embedded companion uses Firebase App Check. This handoff does not send Streamlit session tokens, Firebase Admin credentials, or raw uploaded files.

## Current integration acceptance
- [ ] Configure `SEEPSIGHT_HYBRID_AI_URL` in the deployed Streamlit environment.
- [ ] Confirm the companion URL loads inside Findings and Ask Seepsight.
- [ ] Confirm only the selected finding / latest deterministic answer is prefilled.
- [ ] Confirm App Check works from the actual Firebase Hosting domain.
- [ ] Re-test cloud inference and on-device inference in the embedded Chrome environment.
