import { initializeApp } from 'firebase/app';
import { initializeAppCheck, ReCaptchaEnterpriseProvider } from 'firebase/app-check';
import { getAI, getGenerativeModel, GoogleAIBackend, InferenceMode } from 'firebase/ai';

const env = import.meta.env;
const config = {
  apiKey: env.VITE_FIREBASE_API_KEY,
  authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
  projectId: env.VITE_FIREBASE_PROJECT_ID,
  appId: env.VITE_FIREBASE_APP_ID,
  messagingSenderId: env.VITE_FIREBASE_MESSAGING_SENDER_ID,
  storageBucket: env.VITE_FIREBASE_STORAGE_BUCKET,
};
const required = ['apiKey', 'projectId', 'appId'];
const missing = required.filter((key) => !config[key]);
let app = null;
let appCheckReady = false;
let initError = null;

if (!missing.length) {
  try {
    app = initializeApp(config);
    const debugMode = env.DEV && env.VITE_FIREBASE_APPCHECK_DEBUG === 'true';
    const siteKey = env.VITE_FIREBASE_APPCHECK_RECAPTCHA_ENTERPRISE_SITE_KEY;
    if (debugMode) self.FIREBASE_APPCHECK_DEBUG_TOKEN = true;
    if (!siteKey && !debugMode) {
      throw new Error('Firebase App Check is not configured for this web domain.');
    }
    initializeAppCheck(app, {
      provider: new ReCaptchaEnterpriseProvider(siteKey || 'local-debug-placeholder'),
      isTokenAutoRefreshEnabled: true,
    });
    appCheckReady = true;
  } catch (error) {
    initError = error;
  }
}

export function getFirebaseStatus() {
  if (missing.length) return { ready: false, message: `Missing Firebase web configuration: ${missing.join(', ')}. Copy .env.example to .env.local and add your Firebase Web App values.` };
  if (initError) return { ready: false, message: initError.message };
  if (!appCheckReady) return { ready: false, message: 'Firebase App Check has not initialized.' };
  return { ready: true, message: 'Firebase and App Check initialized.' };
}

export function createHybridModel(cloudFallbackAllowed) {
  const status = getFirebaseStatus();
  if (!status.ready || !app) throw new Error(status.message);
  const ai = getAI(app, { backend: new GoogleAIBackend() });
  return getGenerativeModel(ai, {
    mode: cloudFallbackAllowed ? InferenceMode.PREFER_ON_DEVICE : InferenceMode.ONLY_ON_DEVICE,
  });
}
