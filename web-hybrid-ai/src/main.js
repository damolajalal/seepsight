import './style.css';
import { createHybridModel, createCloudOnlyModel, getFirebaseStatus } from './firebase.js';
import { buildFindingPrompt, buildAssistantPrompt, hasUnsupportedNumbers } from './prompt.js';

const app = document.querySelector('#app');
app.innerHTML = `
<main class="shell">
  <header class="topbar"><a class="brand" href="#"><span class="mark">S</span> Seepsight <small>HYBRID AI</small></a><span id="config" class="pill">Checking setup…</span></header>
  <section class="intro"><p class="eyebrow">EVIDENCE-LED PROCUREMENT INTELLIGENCE</p><h1 id="hero-title">Understand the finding.<br><em>Keep control of your data.</em></h1><p class="lead" id="hero-copy">Turn a verified Seepsight finding into a clear explanation. Your procurement figures remain grounded in the evidence you provide.</p></section>
  <section class="workspace"><div class="section-title"><div><p class="eyebrow" id="mode-label">FINDING EXPLAINER</p><h2 id="form-title">Explain a procurement finding</h2></div><span class="tag">Firebase AI Logic</span></div>
    <form id="form">
      <p id="question-display" class="lead" hidden></p>
      <div class="fields"><label>Supplier or company <input id="supplier" maxlength="160" placeholder="Company or supplier name (optional)"></label><label>Finding type or context <input id="type" maxlength="160" placeholder="e.g. Short delivery"></label></div>
      <label id="facts-label">Verified evidence summary <textarea id="facts" required maxlength="12000" rows="6" placeholder="A concise, verified summary from your Seepsight workspace."></textarea><span class="hint">Use anonymised or synthetic evidence. Do not paste personal, financial or confidential supplier records.</span></label>
      <label id="action-label">What should the explanation focus on? <input id="action" maxlength="500" placeholder="e.g. What should the reviewer verify next?"></label>
      <div class="consent"><strong>Choose where inference may run</strong><p>On-device only keeps the prompt in Chrome. Hybrid mode prefers the local Chrome model and may send the prompt to Google's cloud model only when you consent.</p><span id="device-status" class="pill">Checking local model availability…</span><small id="device-note">On-device AI requires supported desktop Chrome and may be blocked inside embedded frames.</small><label class="check"><input id="consent" type="checkbox"> I consent to cloud fallback for this request if on-device inference cannot run.</label></div>
      <div class="actions"><button id="submit" type="submit" disabled>Explain finding →</button><span>Cloud fallback is off unless you consent above.</span></div>
    </form>
  </section>
  <section id="result" class="result" hidden aria-live="polite"><div class="section-title"><div><p class="eyebrow">AI RESPONSE</p><h2 id="result-title">What this finding means</h2></div><span id="source" class="pill">Waiting</span></div><div id="answer" class="answer-content"></div><small id="note"></small></section>
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
const actionInput = document.querySelector('#action');
let assistantMode = false;

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

function appendInline(parent, text) {
  const pattern = /\*\*(.+?)\*\*/g;
  let cursor = 0;
  let match;
  while ((match = pattern.exec(text)) !== null) {
    if (match.index > cursor) parent.append(document.createTextNode(text.slice(cursor, match.index)));
    const strong = document.createElement('strong');
    strong.textContent = match[1];
    parent.append(strong);
    cursor = pattern.lastIndex;
  }
  if (cursor < text.length) parent.append(document.createTextNode(text.slice(cursor)));
}

function renderStructuredAnswer(markdown) {
  answer.replaceChildren();
  let list = null;
  for (const rawLine of String(markdown).split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line) { list = null; continue; }
    if (/^#{1,3}\s+/.test(line)) {
      list = null;
      const heading = document.createElement('h3');
      appendInline(heading, line.replace(/^#{1,3}\s+/, ''));
      answer.append(heading);
      continue;
    }
    if (/^(?:[-*]|\d+\.)\s+/.test(line)) {
      if (!list) {
        list = document.createElement('ul');
        answer.append(list);
      }
      const item = document.createElement('li');
      appendInline(item, line.replace(/^(?:[-*]|\d+\.)\s+/, ''));
      list.append(item);
      continue;
    }
    list = null;
    const paragraph = document.createElement('p');
    appendInline(paragraph, line);
    answer.append(paragraph);
  }
}

function show(message, route = 'NOTICE', detail = '') {
  result.hidden = false;
  renderStructuredAnswer(message);
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
    const input = {
      supplier: document.querySelector('#supplier').value,
      findingType: document.querySelector('#type').value,
      verifiedFacts: document.querySelector('#facts').value,
      requestedAction: actionInput.value,
    };
    prompt = assistantMode ? buildAssistantPrompt(input) : buildFindingPrompt(input);
  } catch (error) {
    show(error.message, 'INPUT REQUIRED');
    return;
  }

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
      if (!allowCloud) throw localError;
      note.textContent = 'Local model unavailable. Cloud fallback is being attempted because you explicitly consented.';
      response = await createCloudOnlyModel().generateContent(prompt);
    }

    const generatedText = response.response.text();
    const reportedRoute = normaliseInferenceSource(response.response.inferenceSource);
    if (!allowCloud && reportedRoute === 'IN_CLOUD') {
      throw new Error('Privacy protection stopped an unexpected cloud response.');
    }
    const route = allowCloud ? reportedRoute : 'ON_DEVICE';
    if (!generatedText?.trim()) throw new Error('The model returned an empty response.');
    if (hasUnsupportedNumbers(generatedText, prompt)) {
      show('## Response withheld\nThe response introduced a numeric value not present in the supplied verified facts. The original finding is unchanged.', route, 'Numeric consistency guardrail triggered.');
    } else {
      show(generatedText, route, route === 'ON_DEVICE'
        ? 'Processed on this device in Chrome.'
        : route === 'IN_CLOUD'
          ? 'Processed in the cloud through Firebase AI Logic after your consent.'
          : 'The SDK did not report the inference route.');
    }
  } catch (error) {
    show(allowCloud
      ? '## Request failed\nHybrid AI could not complete this request. Check Firebase AI Logic, App Check, network access and model availability.'
      : '## On-device inference unavailable\nThis request was not sent to the cloud because cloud consent was not given.',
      'REQUEST FAILED', error?.message || 'No further error details.');
  } finally {
    consent.disabled = false;
    submit.disabled = false;
    submit.textContent = assistantMode ? 'Ask Hybrid AI →' : 'Explain finding →';
  }
});

/*
 * Accept only the documented context payload from the authenticated Seepsight
 * parent or a trusted Seepsight top-level opener. Never accept HTML or model settings.
 */
window.addEventListener('message', (event) => {
  const trustedStreamlitOrigins = new Set(['https://seepsight.streamlit.app', 'https://traceiq.streamlit.app']);
  const fromParent = event.source === window.parent && trustedStreamlitOrigins.has(event.origin);
  const fromTrustedOpener = event.source === window.opener && trustedStreamlitOrigins.has(event.origin);
  if (!fromParent && !fromTrustedOpener) return;
  const data = event.data;
  const supportedTypes = new Set(['seepsight:explain-finding', 'seepsight:ask-hybrid-ai']);
  if (!data || !supportedTypes.has(data.type) || data.version !== 1) return;
  const fields = {
    supplier: document.querySelector('#supplier'),
    type: document.querySelector('#type'),
    facts: document.querySelector('#facts'),
    action: actionInput,
  };
  const values = {
    supplier: data.supplier,
    type: data.findingType,
    facts: data.verifiedFacts,
    action: data.requestedAction,
  };
  const limits = { supplier: 160, type: 160, facts: 12000, action: 500 };
  for (const key of Object.keys(fields)) {
    if (typeof values[key] !== 'string' || values[key].length > limits[key]) return;
  }
  assistantMode = data.type === 'seepsight:ask-hybrid-ai';
  fields.supplier.value = values.supplier;
  fields.type.value = values.type;
  fields.facts.value = values.facts;
  fields.action.value = values.action;
  if (assistantMode) {
    document.querySelector('.fields').hidden = true;
    document.querySelector('#facts-label').hidden = true;
    document.querySelector('#action-label').hidden = true;
    document.querySelector('#question-display').hidden = false;
    document.querySelector('#question-display').textContent = `Question: ${values.action}`;
    document.querySelector('#hero-title').innerHTML = 'Ask better questions.<br><em>Stay grounded in evidence.</em>';
    document.querySelector('#hero-copy').textContent = 'Hybrid AI has retrieved relevant saved records for this question from your authenticated company workspace.';
    document.querySelector('#mode-label').textContent = 'COMPANY AI ASSISTANT';
    document.querySelector('#form-title').textContent = 'Ask Hybrid AI';
    document.querySelector('#facts-label').firstChild.textContent = 'Retrieved company procurement evidence';
    document.querySelector('#action-label').firstChild.textContent = 'Question supplied by the company workspace';
    actionInput.placeholder = 'Your question is supplied by the company workspace.';
    submit.textContent = 'Ask Hybrid AI →';
    document.querySelector('#result-title').textContent = 'Hybrid AI response';
  }
  show(
    assistantMode
      ? 'Your question-specific company evidence is ready. Choose your privacy setting, then select Ask Hybrid AI.'
      : 'A verified finding summary was received from your Seepsight workspace. Review the summary, choose your inference privacy setting, then select Explain finding.',
    assistantMode ? 'WORKSPACE LOADED' : 'FINDING LOADED'
  );
});
