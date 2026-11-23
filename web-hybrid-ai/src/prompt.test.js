import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFindingPrompt, hasUnsupportedNumbers } from './prompt.js';

test('builds an evidence-first procurement prompt', () => {
  const prompt = buildFindingPrompt({ supplier:'Northstar', findingType:'Short delivery', verifiedFacts:'Ordered 100; received 85; shortage 15 units.' });
  assert.match(prompt, /Use only the supplied facts/);
  assert.match(prompt, /Do not recalculate or alter any metric/);
});
test('rejects empty or oversized evidence', () => {
  assert.throws(() => buildFindingPrompt({ verifiedFacts:' ' }), /Add the verified facts/);
  assert.throws(() => buildFindingPrompt({ verifiedFacts:'x'.repeat(5001) }), /5,000 characters/);
});
test('flags numeric claims absent from supplied evidence', () => {
  const prompt = 'Ordered 100; received 85; shortage 15 units.';
  assert.equal(hasUnsupportedNumbers('The order was 100 and receipt was 85.', prompt), false);
  assert.equal(hasUnsupportedNumbers('The loss is 250,000.', prompt), true);
});
