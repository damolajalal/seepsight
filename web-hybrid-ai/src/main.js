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
      <div class="consent"><strong>Choose where inference may run</strong><p>On-device only keeps the prompt in Chrome. Hybrid mode prefers the local Chrome model and may send the prompt to Google's cloud model only when you consent.</p><label class="check"><input id="consent" type="checkbox"> I consent to cloud fallback for this request if on-device inference cannot run.</label></div>
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
config.textContent = status.ready ? 'Firebase ready' : 'Setup required';
config.classList.toggle('ready', status.ready);
config.title = status.message;
submit.disabled = !status.ready;

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
    const route = normaliseInferenceSource(response.response.inferenceSource);
    if (!generatedText?.trim()) throw new Error('The model returned an empty response.');
    if (route === 'IN_CLOUD' && !allowCloud) {
      throw new Error('Privacy protection stopped a cloud response because this request did not have cloud consent.');
    }
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
