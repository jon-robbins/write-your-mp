import test from 'node:test';
import assert from 'node:assert/strict';
import { createLookupCache } from '../server/lookupCache.mjs';

test('the least recently used entry is dropped once the cache is full', () => {
  const cache = createLookupCache({ maxEntries: 2 });
  cache.set('A1A1A1', 'a');
  cache.set('B2B2B2', 'b');
  cache.get('A1A1A1');
  cache.set('C3C3C3', 'c');
  assert.equal(cache.get('B2B2B2'), undefined);
  assert.equal(cache.get('A1A1A1'), 'a');
  assert.equal(cache.get('C3C3C3'), 'c');
  assert.equal(cache.size, 2);
});
