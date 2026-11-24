import './style.css';
import { createHybridModel, createCloudOnlyModel, getFirebaseStatus } from './firebase.js';
import { buildFindingPrompt, hasUnsupportedNumbers } from './prompt.js';

const app = document.querySelector('#app');
app.innerHTML = `
<main class="shell">
  <header class="topbar"><a class="brand" href="#"><span class="mark">S</span> Seepsight <small>HYBRID AI</small></a><span id="config" class="pill">Checking setup…</span></header>
  <section class="intro"><p class="eyebrow">EVIDENCE-LED PROCUREMENT INTELLIGENCE</p><h1>Understand the finding.<br><em>Keep control of your data.</em></h1><p class="lead">Turn a verified Seepsight finding into a clear explanation. Your procurement figures remain grounded in the evidence you provide.</p></section>
  <section class="workspace"><div class="section-title"><div><p class="eyebrow">FINDING EXPLAINER</p><h2>Explain a procurement finding</h2></div><span class="tag">Firebase AI Logic</span></div>
    <form id="form">
      <div class="fields"><label>Supplier <input id="supplier" maxlength="160" placeholder="Supplier name (optional)"></label><label>Finding type <input id="type" maxlength="160" placeholder="e.g. Short delivery"></label></div>
      <label>Verified evidence summary <textarea id="facts" required maxlength="5000" rows="6" placeholder="Paste a short verified finding summary—not a full spreadsheet. Include exact figures and evidence references."></textarea><span class="hint">Use anonymised or synthetic evidence. Do not paste personal, financial or confidential supplier records.</span></label>
      <label>What should the explanation focus on? <input id="action" maxlength="300" placeholder="e.g. What should the reviewer verify next?"></label>
      <div class="consent"><strong>Choose where inference may run</strong><p>On-device only keeps the prompt in Chrome. Hybrid mode prefers the local Chrome model and may send the prompt to Google's cloud model only when you consent.</p><span id="device-status" class="pill">Checking local model availability…</span><small id="device-note">On-device AI requires supported desktop Chrome and may be blocked inside embedded frames.</small><label class="check"><input id="consent" type="checkbox"> I consent to cloud fallback for this request if on-device inference cannot run.</label></div>
      <div class="actions"><button id="submit" type="submit" disabled>Explain finding →</button><span>Cloud fallback is off unless you consent above.</span></div>
    </form>
  </section>
  <section id="result" class="result" hidden aria-live="polite"><div class="section-title"><div><p class="eyebrow">AI EXPLANATION</p><h2>What this finding means</h2></div><span id="source" class="pill">Waiting</span></div><p id="answer"></p><small id="note"></small></section>
  <footer><span>Evidence first. Privacy choice. Human review.</span><span>Seepsight · Hybrid AI</span></footer>
</main>`;
const status = getFirebaseStatus();
const config = document.querySelector('#config');
const submit = document.querySelector('#submit');
const form = document.querySelector('#form');
const result = document.querySelector('#result');
const answer = document.querySelector('#answer');
const source = document.querySelector('#source');
const note = document.querySelector('#note');
const consent = document.querySelector('#consent');
const deviceStatus = document.querySelector('#device-status');
const deviceNote = document.querySelector('#device-note');
config.textContent = status.ready ? 'Firebase ready' : 'Setup required';
config.classList.toggle('ready', status.ready);
config.title = status.message;
submit.disabled = !status.ready;

async function checkOnDeviceAvailability() {
  if (!globalThis.LanguageModel || typeof globalThis.LanguageModel.availability !== 'function') {
    deviceStatus.textContent = 'Local model API not detected';
    deviceNote.textContent = 'Use desktop Chrome 139+ with compatible hardware: 16 GB RAM and 4 CPU cores, or a GPU with over 4 GB VRAM, plus 22 GB free disk space. Chrome on Android is not supported.';
    return;
  }
  try {
    const availability = await globalThis.LanguageModel.availability({
      expectedInputs: [{ type: 'text', languages: ['en'] }],
      expectedOutputs: [{ type: 'text', languages: ['en'] }],
    });
    const messages = {
      available: ['Gemini Nano available', 'The browser reports that the local model is ready.'],
      downloadable: ['Gemini Nano can be downloaded', 'The first request may download the model and take several minutes.'],
      downloading: ['Gemini Nano is downloading', 'Wait for the browser model download to finish.'],
      unavailable: ['Gemini Nano unavailable here', 'This browser, device, model setting, or embedded-frame permission may not support local inference. Open the companion directly in supported desktop Chrome to test.'],
    };
    const [label, detail] = messages[availability] || ['Local model status unknown', `Browser availability response: ${String(availability)}`];
    deviceStatus.textContent = label;
    deviceNote.textContent = detail;
  } catch (error) {
    deviceStatus.textContent = 'Could not check local model';
    deviceNote.textContent = error?.message || 'The browser did not provide an availability result.';
  }
}
void checkOnDeviceAvailability();

function show(message, route = 'NOTICE', detail = '') {
  result.hidden = false;
  answer.textContent = message;
  source.textContent = route;
  note.textContent = detail;
}

function normaliseInferenceSource(value) {
  const sourceValue = String(value || '').toLowerCase();
  if (sourceValue === 'on_device') return 'ON_DEVICE';
  if (sourceValue === 'in_cloud') return 'IN_CLOUD';
  return 'SOURCE NOT REPORTED';
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  if (!status.ready) return;
  let prompt;
  try {
    prompt = buildFindingPrompt({
      supplier: document.querySelector('#supplier').value,
      findingType: document.querySelector('#type').value,
      verifiedFacts: document.querySelector('#facts').value,
      requestedAction: document.querySelector('#action').value,
    });
  } catch (error) {
    show(error.message, 'INPUT REQUIRED');
    return;
  }

  // Snapshot explicit consent at click time; do not infer consent from model availability.
  const allowCloud = consent.checked === true;
  submit.disabled = true;
  consent.disabled = true;
  submit.textContent = 'Preparing secure inference…';
  show('Preparing the selected inference path. The first local model run may take time.', 'STARTING');

  try {
    const localModel = createHybridModel(allowCloud);
    let response;
    try {
      await localModel.initializeDeviceModel((progress) => {
        note.textContent = `Preparing on-device model: ${Math.round(progress * 100)}% downloaded.`;
      });
      response = await localModel.generateContent(prompt);
    } catch (localError) {
      // Without explicit consent, stop here. No cloud-capable model is created or called.
      if (!allowCloud) throw localError;
      note.textContent = 'Local model unavailable. Cloud fallback is being attempted because you explicitly consented.';
      response = await createCloudOnlyModel().generateContent(prompt);
    }

    const generatedText = response.response.text();
    const reportedRoute = normaliseInferenceSource(response.response.inferenceSource);
    // ONLY_ON_DEVICE cannot use the cloud. The SDK may omit inferenceSource for this mode.
    if (!allowCloud && reportedRoute === 'IN_CLOUD') {
      throw new Error('Privacy protection stopped an unexpected cloud response.');
    }
    const route = allowCloud ? reportedRoute : 'ON_DEVICE';
    if (!generatedText?.trim()) throw new Error('The model returned an empty response.');
    if (hasUnsupportedNumbers(generatedText, prompt)) {
      show('Response withheld: it introduced a numeric value not present in the supplied facts. The original finding is unchanged.', route, 'Numeric consistency guardrail triggered.');
    } else {
      show(generatedText, route, route === 'ON_DEVICE'
        ? 'Processed on this device in Chrome.'
        : route === 'IN_CLOUD'
          ? 'Processed in the cloud through Firebase AI Logic after your consent.'
          : 'The SDK did not report the inference route.');
    }
  } catch (error) {
    show(allowCloud
      ? 'Hybrid request failed. Check Firebase AI Logic, App Check, network access and model availability.'
      : 'On-device inference is unavailable. This request was not sent to the cloud because cloud consent was not given.',
      'REQUEST FAILED', error?.message || 'No further error details.');
  } finally {
    consent.disabled = false;
    submit.disabled = false;
    submit.textContent = 'Explain finding →';
  }
});

/*
 * Receive a minimal, verified finding summary from the authenticated Seepsight
 * workspace. Accept messages only from the immediate embedding parent and only
 * the documented payload shape; never accept arbitrary HTML or model settings.
 */
window.addEventListener('message', (event) => {
  const trustedStreamlitOrigins = new Set(['https://seepsight.streamlit.app', 'https://traceiq.streamlit.app']);
  const fromParent = event.source === window.parent;
  const fromTrustedOpener = event.source === window.opener && trustedStreamlitOrigins.has(event.origin);
  if (!fromParent && !fromTrustedOpener) return;
  const data = event.data;
  if (!data || data.type !== 'seepsight:explain-finding' || data.version !== 1) return;
  const fields = {
    supplier: document.querySelector('#supplier'),
    type: document.querySelector('#type'),
    facts: document.querySelector('#facts'),
    action: document.querySelector('#action'),
  };
  const values = {
    supplier: data.supplier,
    type: data.findingType,
    facts: data.verifiedFacts,
    action: data.requestedAction,
  };
  const limits = { supplier: 160, type: 160, facts: 5000, action: 300 };
  for (const key of Object.keys(fields)) {
    if (typeof values[key] !== 'string' || values[key].length > limits[key]) return;
  }
  fields.supplier.value = values.supplier;
  fields.type.value = values.type;
  fields.facts.value = values.facts;
  fields.action.value = values.action;
  show('A verified finding summary was received from your Seepsight workspace. Review it, choose your inference privacy setting, then select Explain finding.', 'FINDING LOADED');
});
