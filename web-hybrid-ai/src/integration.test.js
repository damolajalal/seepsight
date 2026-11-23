import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
const read = (name) => readFile(new URL(name, import.meta.url), 'utf8');
test('Firebase AI Logic implements consent-gated hybrid and on-device modes', async () => {
  const source = await read('./firebase.js');
  const main = await read('./main.js');
  assert.match(source, /from 'firebase\/ai'/);
  assert.match(source, /InferenceMode\.PREFER_ON_DEVICE/);
  assert.match(source, /InferenceMode\.ONLY_ON_DEVICE/);
  assert.match(main, /await model\.initializeDeviceModel/);
  assert.match(main, /await model\.generateContent\(prompt\)/);
  assert.match(main, /inferenceSource/);
});
test('App Check is initialized before AI requests are made available', async () => {
  const source = await read('./firebase.js');
  assert.match(source, /initializeAppCheck/);
  assert.match(source, /ReCaptchaEnterpriseProvider/);
  assert.match(source, /if \(!status\.ready \|\| !app\)/);
});
