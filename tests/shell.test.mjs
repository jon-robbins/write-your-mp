import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { app, createApp, frameAncestors } from '../server/index.mjs';

test('GET / redirects to the campaign path', async () => {
  const response = await request(app).get('/');
  assert.equal(response.status, 302);
  assert.equal(response.headers.location, '/campaign/');
});

test('GET /campaign/ serves the Vite page root', async () => {
  const response = await request(app).get('/campaign/');
  assert.equal(response.status, 200);
  assert.match(response.text, /id="root"/);
});

test('GET /healthz returns healthy', async () => {
  const response = await request(app).get('/healthz');
  assert.equal(response.status, 200);
});

test('pages may only be framed by the service itself unless FRAME_ANCESTORS allows more', async () => {
  const response = await request(app).get('/campaign/');
  assert.match(response.headers['content-security-policy'], /(^|; )frame-ancestors 'self'(;|$)/);
  const embedded = await request(createApp({ framing: frameAncestors('https://example.org, https://www.example.org') })).get('/campaign/');
  assert.match(embedded.headers['content-security-policy'], /(^|; )frame-ancestors 'self' https:\/\/example\.org https:\/\/www\.example\.org(;|$)/);
});

test('FRAME_ANCESTORS ignores anything but plain https origins', () => {
  assert.equal(frameAncestors("https://ok.example * 'unsafe-inline' http://plain.example https://x.example/path; script-src"), "frame-ancestors 'self' https://ok.example");
});

test('the old placeholder path is gone', async () => {
  const response = await request(app).get('/placeholder-name/');
  assert.equal(response.status, 404);
});

test('the campaign page is never cached or revalidated to a stale copy', async () => {
  const first = await request(app).get('/campaign/');
  assert.equal(first.headers['cache-control'], 'no-store');
  assert.notEqual(first.headers.etag, 'W/"35d-49773873e8"');
  assert.equal(first.headers['last-modified'], undefined);
  const conditional = await request(app).get('/campaign/')
    .set('If-None-Match', 'W/"35d-49773873e8"')
    .set('If-Modified-Since', 'Tue, 01 Jan 1980 00:00:00 GMT');
  assert.equal(conditional.status, 200);
  assert.match(conditional.text, /id="root"/);
});
