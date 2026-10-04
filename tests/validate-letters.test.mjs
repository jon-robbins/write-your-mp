import test from 'node:test';
import assert from 'node:assert/strict';
import { validateLetters } from '../scripts/validate-letters.mjs';

const valid = [{ id: 'ok', subject: 'Subject', body: 'Body', status: 'preview' }];

test('validation accepts preview letters', () => {
  assert.deepEqual(validateLetters(valid), []);
});

test('validation rejects duplicate IDs', () => {
  const errors = validateLetters([{ ...valid[0] }, { ...valid[0] }]);
  assert.ok(errors.some((error) => /duplicate id/i.test(error)));
});

test('validation rejects a blank subject', () => {
  const errors = validateLetters([{ ...valid[0], subject: '  ' }]);
  assert.ok(errors.some((error) => /subject/i.test(error)));
});

test('validation rejects a blank body', () => {
  const errors = validateLetters([{ ...valid[0], body: '\n' }]);
  assert.ok(errors.some((error) => /body/i.test(error)));
});

test('validation rejects unknown merge tokens', () => {
  const errors = validateLetters([{ ...valid[0], body: 'Hello {unknownToken}' }]);
  assert.ok(errors.some((error) => /unknown token/i.test(error)));
});

test('validation rejects an empty library', () => {
  const errors = validateLetters([]);
  assert.ok(errors.some((error) => /at least one/i.test(error)));
});

test('release validation rejects preview letters', () => {
  const errors = validateLetters(valid, { release: true });
  assert.ok(errors.some((error) => /preview/i.test(error)));
});

const factual = {
  id: 'f', status: 'approved', subject: 'Application delay for Teo Castell',
  body: 'Dear {mpName},\n\nAs a constituent of {riding}: Teo Castell, stateless, privately sponsored by Northbridge Newcomer Alliance, his permanent residence application held in security screening for 11 months, sponsors ready since March 2026, living in Lisbon, Immigration, Refugees and Citizenship Canada, the Minister of Immigration.\n\nSincerely,\n\n{firstName} {lastName}\n{street}\n{city}, {province} {postalCode}',
};

test('release validation accepts a letter with every key fact', () => {
  assert.deepEqual(validateLetters([factual], { release: true }), []);
});

test('release validation rejects a letter missing a key fact', () => {
  const errors = validateLetters([{ ...factual, body: factual.body.replace('Northbridge Newcomer Alliance', 'a nonprofit') }], { release: true });
  assert.ok(errors.some((error) => /Northbridge Newcomer Alliance/.test(error)));
});

test('release validation rejects a letter without the full signature', () => {
  const errors = validateLetters([{ ...factual, body: factual.body.replace('{street}\n', '') }], { release: true });
  assert.ok(errors.some((error) => /signature/i.test(error)));
});

test('riding-specific letters are held to the same facts', () => {
  const own = { ...factual, ridings: ['Ottawa Centre'] };
  assert.deepEqual(validateLetters([own], { release: true }), []);
});

test('validation rejects a malformed ridings list', () => {
  const errors = validateLetters([{ ...valid[0], ridings: 'Ottawa Centre' }]);
  assert.ok(errors.some((error) => /ridings/i.test(error)));
});

for (const [fact, text] of [
  ['stateless', 'stateless, '],
  ['private sponsorship', 'privately sponsored by '],
  ['permanent residence', 'permanent residence '],
  ['security screening', 'security screening'],
  ['March 2026', 'March 2026'],
  ['Lisbon', 'Lisbon'],
]) {
  test(`release validation requires ${fact}`, () => {
    const errors = validateLetters([{ ...factual, body: factual.body.replace(text, '') }], { release: true });
    assert.ok(errors.some((error) => error.includes(`missing ${fact}`)), errors.join('\n'));
  });
}

test('release validation accepts "11-month" as the delay', () => {
  const hyphenated = { ...factual, body: factual.body.replace('11 months', 'the 11-month delay') };
  assert.deepEqual(validateLetters([hyphenated], { release: true }), []);
});

for (const [claim, phrase] of [
  ['praise', 'an acclaimed community leader'],
  ['praise', 'he would be a model citizen'],
  ['record', 'a vetted applicant'],
  ['record', 'travelled without incident'],
  ['record', 'a clean, documented travel history'],
  ['record', 'a history of safe international travel'],
  ['record', 'not a high-risk profile'],
  ['requested', 'No additional information has been requested'],
  ['requested', 'without any request for additional information'],
  ['specifics', 'he already has a job offer in Ottawa'],
  ['specifics', 'his family in Canada is waiting for him'],
  ['sender', 'I am a long-time supporter of refugee sponsorship'],
  ['sender', 'As a volunteer with the Alliance'],
  ['markdown', 'his sponsors, *Northbridge Newcomer Alliance*'],
]) {
  test(`release validation rejects claims the original letter does not make (${claim}: "${phrase}")`, () => {
    const errors = validateLetters([{ ...factual, body: factual.body.replace('Sincerely,', `${phrase}.\n\nSincerely,`) }], { release: true });
    assert.ok(errors.some((error) => /must not/i.test(error)), `no error for "${phrase}"`);
  });
}

test('release validation still accepts what the original says about missing information', () => {
  const plain = { ...factual, body: factual.body.replace('Sincerely,', 'No additional information has been provided. He has no passport and no citizenship.\n\nSincerely,') };
  assert.deepEqual(validateLetters([plain], { release: true }), []);
});
