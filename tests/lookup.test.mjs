import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../server/index.mjs';

const representPayload = {
  representatives_centroid: [{
    name: 'Alex Example',
    district_name: 'Ottawa Centre',
    elected_office: 'MP',
    related: { representative_set_url: '/representative-sets/house-of-commons/' },
    email: 'alex@example.ca',
    url: 'https://example.ca/alex',
  }],
};

test('lookup maps a valid postal code and sends only the normalized code upstream', async () => {
  const calls = [];
  const app = createApp({ fetch: async (...args) => {
    calls.push(args);
    return new Response(JSON.stringify(representPayload), { status: 200 });
  } });

  const response = await request(app)
    .post('/campaign/api/lookup-mp')
    .send({ postalCode: 'K1A 0B1', firstName: 'Private', address: 'Private' });

  assert.equal(response.status, 200);
  assert.deepEqual(response.body, {
    status: 'found',
    mp: { name: 'Alex Example', riding: 'Ottawa Centre', email: 'alex@example.ca', profileUrl: 'https://example.ca/alex' },
  });
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], 'https://represent.opennorth.ca/postcodes/K1A0B1/');
  assert.deepEqual(Object.keys(calls[0][1]), ['signal']);
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('malformed postal codes do not call Represent', async () => {
  let calls = 0;
  const app = createApp({ fetch: async () => { calls += 1; return new Response('{}'); } });
  const response = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'not postal' });
  assert.equal(response.status, 400);
  assert.deepEqual(response.body, { status: 'invalid' });
  assert.equal(calls, 0);
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('upstream failures return unavailable without caching', async () => {
  const app = createApp({ fetch: async () => new Response('upstream error', { status: 503 }) });
  const response = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  assert.equal(response.status, 503);
  assert.deepEqual(response.body, { status: 'unavailable' });
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('upstream timeout or fetch errors return unavailable', async () => {
  const app = createApp({ fetch: async () => { throw new Error('timed out'); } });
  const response = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  assert.equal(response.status, 503);
  assert.deepEqual(response.body, { status: 'unavailable' });
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('fetch errors on the fixed campaign route never fall through to static 404', async () => {
  const app = createApp({ fetchImpl: async () => { throw new Error('network unavailable'); } });
  const response = await request(app)
    .post('/campaign/api/lookup-mp')
    .set('Content-Type', 'application/json')
    .send({ postalCode: 'K1A0B1' });
  assert.equal(response.status, 503);
  assert.deepEqual(response.body, { status: 'unavailable' });
  assert.equal(response.headers['cache-control'], 'no-store');
});

test('repeat lookups of a postal code are answered from the cache, however it is typed', async () => {
  let calls = 0;
  const app = createApp({ fetch: async () => { calls += 1; return new Response(JSON.stringify(representPayload), { status: 200 }); } });
  const first = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A 0B1' });
  const second = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'k1a0b1' });
  assert.equal(calls, 1);
  assert.deepEqual(second.body, first.body);
  assert.equal(second.status, 200);
  assert.equal(second.headers['cache-control'], 'no-store');
});

test('not-found answers are cached too, since Represent did answer', async () => {
  let calls = 0;
  const app = createApp({ fetch: async () => { calls += 1; return new Response('{}', { status: 200 }); } });
  await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  const second = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  assert.equal(calls, 1);
  assert.deepEqual(second.body, { status: 'not_found' });
});

test('a failed lookup is retried upstream next time rather than cached', async () => {
  let calls = 0;
  const app = createApp({ fetch: async () => {
    calls += 1;
    return calls === 1 ? new Response('rate limited', { status: 429 }) : new Response(JSON.stringify(representPayload), { status: 200 });
  } });
  const first = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  const second = await request(app).post('/campaign/api/lookup-mp').send({ postalCode: 'K1A0B1' });
  assert.equal(first.status, 503);
  assert.equal(second.body.status, 'found');
  assert.equal(calls, 2);
});
