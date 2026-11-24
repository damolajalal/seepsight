import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const read = (name) => readFile(new URL(name, import.meta.url), 'utf8');

test('cloud fallback is explicitly consent-gated', async () => {
  const source = await read('./firebase.js');
  const main = await read('./main.js');
  assert.match(source, /cloudFallbackAllowed \? InferenceMode\.PREFER_ON_DEVICE : InferenceMode\.ONLY_ON_DEVICE/);
  assert.match(source, /InferenceMode\.ONLY_IN_CLOUD/);
  assert.match(source, /expectedInputs: \[\{ type: 'text', languages: \['en'\] \}\]/);
  assert.match(main, /const allowCloud = consent\.checked === true/);
  assert.match(main, /if \(!allowCloud\) throw localError/);
  assert.match(main, /createCloudOnlyModel\(\)\.generateContent\(prompt\)/);
  assert.match(main, /reportedRoute === 'IN_CLOUD' && !allowCloud/);
  assert.match(main, /const route = allowCloud \? reportedRoute : 'ON_DEVICE'/);
});

test('inference source values from Firebase are normalised for display', async () => {
  const main = await read('./main.js');
  assert.match(main, /sourceValue === 'on_device'/);
  assert.match(main, /sourceValue === 'in_cloud'/);
  assert.match(main, /return 'ON_DEVICE'/);
  assert.match(main, /return 'IN_CLOUD'/);
  assert.match(main, /LanguageModel\.availability/);
  assert.match(main, /trustedStreamlitOrigins/);
});

test('App Check is initialized before AI requests are made available', async () => {
  const source = await read('./firebase.js');
  assert.match(source, /initializeAppCheck/);
  assert.match(source, /ReCaptchaEnterpriseProvider/);
  assert.match(source, /if \(!status\.ready \|\| !app\)/);
});


test('embedded Seepsight context accepts only a bounded parent message', async () => {
  const main = await read('./main.js');
  assert.match(main, /event\.source !== window\.parent/);
  assert.match(main, /seepsight:explain-finding/);
  assert.match(main, /data\.version !== 1/);
  assert.match(main, /facts: data\.verifiedFacts/);
  assert.match(main, /values\[key\]\.length > limits\[key\]/);
});


test('Firebase Hosting allows only the Seepsight workspace to embed the companion', async () => {
  const config = await readFile(new URL('../../firebase.json', import.meta.url), 'utf8');
  assert.match(config, /frame-ancestors 'self' https:\/\/seepsight\.streamlit\.app https:\/\/traceiq\.streamlit\.app/);
  assert.doesNotMatch(config, /X-Frame-Options/);
});
