# Phase 7 — Firebase AI Logic Hybrid Web Integration

Phase 7 adds `web-hybrid-ai/` as a separate Web/Chrome companion. The existing Streamlit application, nine pages, Python procurement engine and earlier AI integrations remain in place. Ask Seepsight exposes an optional link only when `SEEPSIGHT_HYBRID_AI_URL` is configured.

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
