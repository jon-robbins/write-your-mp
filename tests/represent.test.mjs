import test from 'node:test';
import assert from 'node:assert/strict';
import { mapRepresent, normalizePostalCode } from '../server/represent.mjs';

test('normalizes valid Canadian postal codes and rejects invalid patterns', () => {
  assert.equal(normalizePostalCode('K1A 0B1'), 'K1A0B1');
  assert.equal(normalizePostalCode('k1a0b1'), 'K1A0B1');
  assert.equal(normalizePostalCode('12345'), null);
  assert.equal(normalizePostalCode('D5L 2G1'), null);
  assert.equal(normalizePostalCode('K1A-0B1'), null);
});

test('maps the elected federal MP from centroid representatives', () => {
  const result = mapRepresent({
    representatives_centroid: [
      {
        name: 'Alex Example',
        district_name: 'Ottawa Centre',
        elected_office: 'MP',
        related: { representative_set_url: '/representative-sets/house-of-commons/' },
        email: 'alex@example.ca',
        url: 'https://example.ca/alex',
      },
      {
        name: 'Pat Provincial',
        district_name: 'Ottawa Centre',
        elected_office: 'MLA',
        related: { representative_set_url: '/representative-sets/british-columbia-legislative-assembly/' },
        email: 'pat@example.ca',
        url: 'https://example.ca/pat',
      },
    ],
  });

  assert.deepEqual(result, {
    status: 'found',
    mp: {
      name: 'Alex Example',
      riding: 'Ottawa Centre',
      email: 'alex@example.ca',
      profileUrl: 'https://example.ca/alex',
    },
  });
});

test('maps concordance MPs and deduplicates emails case-insensitively', () => {
  const result = mapRepresent({
    representatives_concordance: [
      {
        name: 'Alex Example',
        district_name: 'Ottawa Centre',
        elected_office: 'MP',
        related: { representative_set_url: '/representative-sets/house-of-commons/' },
        email: 'Alex@Example.ca',
        url: 'https://example.ca/alex',
      },
      {
        name: 'Alex Duplicate',
        district_name: 'Ottawa Centre',
        elected_office: 'MP',
        related: { representative_set_url: '/representative-sets/house-of-commons/' },
        email: 'alex@example.ca',
        url: 'https://example.ca/alex-duplicate',
      },
      {
        name: 'Jordan Other',
        district_name: 'Ottawa Centre',
        elected_office: 'MP',
        related: { representative_set_url: '/representative-sets/house-of-commons/' },
        email: 'jordan@example.ca',
        url: 'https://example.ca/jordan',
      },
    ],
  });

  assert.equal(result.status, 'multiple');
  assert.equal(result.mps.length, 2);
  assert.deepEqual(result.mps.map(({ email }) => email), ['Alex@Example.ca', 'jordan@example.ca']);
});

test('returns not_found when no eligible MP is present', () => {
  assert.deepEqual(mapRepresent({ representatives_centroid: [] }), { status: 'not_found' });
});
