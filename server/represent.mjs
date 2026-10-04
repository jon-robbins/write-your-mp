const POSTAL_CODE_PATTERN = /^[ABCEGHJ-NPRSTVXY][0-9][ABCEGHJ-NPRSTV-Z][0-9][ABCEGHJ-NPRSTV-Z][0-9]$/;
const HOUSE_OF_COMMONS_SET = '/representative-sets/house-of-commons/';

export function normalizePostalCode(input) {
  if (typeof input !== 'string') return null;

  const postalCode = input.replace(/\s/g, '').toUpperCase();
  return POSTAL_CODE_PATTERN.test(postalCode) ? postalCode : null;
}

function isFederalMp(representative) {
  return representative?.elected_office === 'MP'
    && representative?.related?.representative_set_url === HOUSE_OF_COMMONS_SET
    && typeof representative?.email === 'string'
    && representative.email.trim() !== '';
}

function mapMp(representative) {
  return {
    name: representative.name,
    riding: representative.district_name,
    email: representative.email,
    // The page links to this, so only an https address may pass through.
    profileUrl: typeof representative.url === 'string' && /^https:\/\//i.test(representative.url) ? representative.url : undefined,
  };
}

export function mapRepresent(payload = {}) {
  const representatives = [
    ...(Array.isArray(payload.representatives_centroid) ? payload.representatives_centroid : []),
    ...(Array.isArray(payload.representatives_concordance) ? payload.representatives_concordance : []),
  ].filter(isFederalMp);

  const uniqueMps = [];
  const emails = new Set();
  for (const representative of representatives) {
    const emailKey = representative.email.trim().toLowerCase();
    if (emails.has(emailKey)) continue;
    emails.add(emailKey);
    uniqueMps.push(mapMp(representative));
  }

  if (uniqueMps.length === 0) return { status: 'not_found' };
  if (uniqueMps.length === 1) return { status: 'found', mp: uniqueMps[0] };
  return { status: 'multiple', mps: uniqueMps };
}
