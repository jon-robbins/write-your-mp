import test from 'node:test';
import assert from 'node:assert/strict';
import request from 'supertest';
import { createApp } from '../server/index.mjs';
import { demoRepresentFetch } from '../server/demoRepresent.mjs';

const lookup = (app, postalCode) => request(app).post('/campaign/api/lookup-mp').send({ postalCode });

test('demo mode answers lookups with fictional MPs and never calls OpenNorth', async () => {
  const app = createApp({ fetch: demoRepresentFetch });
  const general = await lookup(app, 'K2B 1A1');
  assert.equal(general.body.status, 'found');
  assert.equal(general.body.mp.email, 'sam-taylor@example.org');
  const home = await lookup(app, 'K1P 1A1');
  assert.equal(home.body.mp.riding, 'Ottawa Centre');
  const split = await lookup(app, 'K2C 0A1');
  assert.equal(split.body.status, 'multiple');
  assert.equal(split.body.mps.length, 2);
});

test('the demo home riding gets its own letters', async () => {
  const app = createApp({ fetch: demoRepresentFetch });
  const response = await request(app).get('/campaign/api/letter').query({ riding: 'Ottawa Centre' });
  assert.match(response.body.id, /^home-/);
});
