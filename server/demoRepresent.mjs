// Demo mode (`--demo` or DEMO_LOOKUP=1): answers MP lookups with fictional MPs instead of calling OpenNorth, so the
// tool runs offline and screenshots show no real people. Responses have the same shape as Represent's.
const HOUSE_OF_COMMONS = { representative_set_url: '/representative-sets/house-of-commons/' };

function mp(name, riding) {
  const slug = name.toLowerCase().replace(/[^a-z]+/g, '-');
  return { name, district_name: riding, elected_office: 'MP', email: `${slug}@example.org`, url: `https://example.org/mps/${slug}`, related: HOUSE_OF_COMMONS };
}

// K1P: the campaign's home riding, which gets its own letters. K2C: a postal code that spans two ridings.
export function demoRepresentatives(postalCode) {
  if (/^K1P/.test(postalCode)) return [mp('Jordan Lee', 'Ottawa Centre')];
  if (/^K2C/.test(postalCode)) return [mp('Priya Natarajan', 'Riverside North'), mp('Daniel Okafor', 'Riverside South')];
  return [mp('Sam Taylor', 'Riverside North')];
}

export async function demoRepresentFetch(url) {
  const postalCode = String(url).split('/').filter(Boolean).pop();
  return new Response(JSON.stringify({ representatives_centroid: demoRepresentatives(postalCode) }), {
    status: 200, headers: { 'Content-Type': 'application/json' },
  });
}
