# BuildHybridAI — Phase 7 completion checklist

## Source implementation
- [x] Separate Web/Chrome companion under `web-hybrid-ai/`.
- [x] Firebase AI Logic SDK integration.
- [x] Consent-gated on-device / cloud-fallback inference modes.
- [x] App Check initialization and reCAPTCHA Enterprise configuration.
- [x] Evidence-first prompt and numeric consistency guardrail.
- [x] Python Streamlit workspace remains the main procurement application.

## Local and live verification
- [ ] Install npm dependencies and run the production Vite build from the current feature branch.
- [ ] Configure production Firebase Web App values and the exact-domain reCAPTCHA Enterprise site key.
- [ ] Verify App Check enforcement in Firebase Console.
- [ ] Deploy Hosting and verify the public URL.
- [ ] Capture a real on-device inference and confirm the Chrome model/version.
- [ ] Capture a consented cloud-fallback inference and verify the SDK-reported source.
- [ ] Record the demo and complete any external submission materials.

Do not describe Phase 7 as fully live until the unchecked deployment and browser checks have passed.
