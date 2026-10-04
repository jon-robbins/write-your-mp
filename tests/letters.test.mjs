import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../server/index.mjs';
import { letterPool, pickLetter } from '../server/letters.mjs';

const general = [
  { id: 'g1', subject: 'S1', body: 'B1', status: 'approved' },
  { id: 'g2', subject: 'S2', body: 'B2', status: 'approved' },
];
const home = { id: 've1', subject: 'SV', body: 'BV', status: 'approved', ridings: ['Ottawa Centre'] };
const letters = [...general, home];

test('a riding with its own letters only gets those letters', () => {
  assert.deepEqual(letterPool(letters, 'Ottawa Centre').map((l) => l.id), ['ve1']);
});

test('other ridings get only the general letters', () => {
  assert.deepEqual(letterPool(letters, 'Kanata').map((l) => l.id), ['g1', 'g2']);
  assert.deepEqual(letterPool(letters, undefined).map((l) => l.id), ['g1', 'g2']);
});

test('pickLetter avoids the excluded letter when another is available', () => {
  assert.equal(pickLetter(letters, { riding: 'Kanata', exclude: 'g1', random: () => 0 }).letter.id, 'g2');
  assert.equal(pickLetter(letters, { riding: 'Ottawa Centre', exclude: 've1', random: () => 0 }).letter.id, 've1');
});

test('pickLetter reports the pool size so the page knows whether a new draft is possible', () => {
  assert.equal(pickLetter(letters, { riding: 'Kanata', random: () => 0.99 }).poolSize, 2);
});

test('GET letter returns one template, its pool size, and is never cached', async () => {
  const app = createApp({ letters, random: () => 0 });
  const response = await request(app).get('/campaign/api/letter').query({ riding: 'Ottawa Centre' });
  assert.equal(response.status, 200);
  assert.deepEqual(response.body, { id: 've1', subject: 'SV', body: 'BV', poolSize: 1 });
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('GET letter never exposes the whole library', async () => {
  const app = createApp({ letters, random: () => 0 });
  const response = await request(app).get('/campaign/api/letter');
  assert.equal(JSON.stringify(response.body).includes('B2'), false);
});

test('the shipped library validates for release and has an Ottawa Centre letter', async () => {
  const { validateLetters } = await import('../scripts/validate-letters.mjs');
  const { readFile } = await import('node:fs/promises');
  const shipped = JSON.parse(await readFile(new URL('../server/letters.json', import.meta.url), 'utf8'));
  assert.deepEqual(validateLetters(shipped, { release: true }), []);
  assert.ok(letterPool(shipped, 'Ottawa Centre').length > 0);
  assert.ok(letterPool(shipped, 'Kanata').length > 0);
  assert.ok(letterPool(shipped, 'Ottawa Centre').every((l) => /Northbridge Newcomer Alliance is based|based here in our riding/.test(l.body)));
});
