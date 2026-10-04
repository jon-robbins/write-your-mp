import test from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import request from 'supertest';
import { createApp } from '../server/index.mjs';

const represent = (url) => async () => new Response(JSON.stringify({
  representatives_centroid: [{
    name: 'Alex Example', district_name: 'Ottawa Centre', elected_office: 'MP', email: 'alex@example.ca', url,
    related: { representative_set_url: '/representative-sets/house-of-commons/' },
  }],
}), { status: 200 });

const directive = (policy, name) => policy.split(';').map((part) => part.trim()).find((part) => part.startsWith(`${name} `));

test('every response carries hardening headers and hides the framework', async () => {
  for (const path of ['/campaign/', '/campaign/api/letter?riding=X', '/healthz']) {
    const response = await request(createApp()).get(path);
    assert.equal(response.headers['x-powered-by'], undefined, path);
    assert.equal(response.headers['x-content-type-options'], 'nosniff', path);
    assert.equal(response.headers['referrer-policy'], 'strict-origin-when-cross-origin', path);
    const policy = response.headers['content-security-policy'];
    assert.equal(directive(policy, 'default-src'), "default-src 'self'", path);
    assert.equal(directive(policy, 'object-src'), "object-src 'none'", path);
    assert.equal(directive(policy, 'base-uri'), "base-uri 'none'", path);
    assert.equal(directive(policy, 'frame-ancestors'), "frame-ancestors 'self'", path);
  }
});

test('the page allows only its own scripts and the exact inline config it ships', async () => {
  const response = await request(createApp()).get('/campaign/');
  const scriptSrc = directive(response.headers['content-security-policy'], 'script-src');
  const inline = [...response.text.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map((match) => match[1]);
  assert.equal(scriptSrc, ["script-src 'self'", ...inline.map((code) => `'sha256-${createHash('sha256').update(code).digest('base64')}'`)].join(' '));
  assert.doesNotMatch(scriptSrc, /unsafe-inline|unsafe-eval/);
});

test('malformed JSON gets a short JSON error, not an HTML page', async () => {
  const response = await request(createApp()).post('/campaign/api/lookup-mp').set('Content-Type', 'application/json').send('{bad');
  assert.equal(response.status, 400);
  assert.deepEqual(response.body, { status: 'invalid' });
});

test('one visitor cannot spend the shared MP lookup limit', async () => {
  let upstreamCalls = 0;
  const app = createApp({ fetch: async (...args) => { upstreamCalls += 1; return represent('https://example.ca/alex')(...args); }, lookupLimit: 3 });
  const codes = ['K1A0B1', 'K1A0B2', 'K1A0B3', 'K1A0B4', 'K1A0B5'];
  const statuses = [];
  for (const postalCode of codes) statuses.push((await request(app).post('/campaign/api/lookup-mp').send({ postalCode })).status);
  assert.deepEqual(statuses, [200, 200, 200, 429, 429]);
  assert.equal(upstreamCalls, 3);
  const limited = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B6' });
  assert.deepEqual(limited.body, { status: 'unavailable' });
});

test('letter requests are rate limited per visitor too', async () => {
  const app = createApp({ letterLimit: 2 });
  const statuses = [];
  for (let i = 0; i < 3; i += 1) statuses.push((await request(app).get('/campaign/api/letter?riding=X')).status);
  assert.deepEqual(statuses, [200, 200, 429]);
});

test('only https profile links from Represent reach the page', async () => {
  for (const [url, expected] of [['https://example.ca/alex', 'https://example.ca/alex'], ['javascript:alert(1)', undefined], ['http://example.ca/alex', undefined]]) {
    const response = await request(createApp({ fetch: represent(url) })).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
    assert.equal(response.body.mp.profileUrl, expected, url);
  }
});
