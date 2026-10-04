import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

export const SUPPORTED_TOKENS = new Set([
  'mpName', 'riding', 'firstName', 'lastName', 'street', 'city', 'province', 'postalCode',
]);

// Every released letter must keep these facts so reworded variants cannot drift from the original letter.
export const REQUIRED_FACTS = [
  ['Teo Castell', /Teo\b[\s\S]*Castell|Castell/],
  ['stateless', /stateless/i],
  ['Northbridge Newcomer Alliance', /Northbridge Newcomer Alliance/],
  ['private sponsorship', /privately sponsor|private sponsor/i],
  ['permanent residence', /permanent residen(ce|t)/i],
  ['security screening', /security screening/i],
  ['March 2026', /March 2026/],
  ['Lisbon', /Lisbon/],
  ['11 months', /\b(11|eleven)[ -]months?\b/i],
  ['Immigration, Refugees and Citizenship Canada', /Immigration, Refugees and Citizenship Canada|\bIRCC\b/],
  ['Minister of Immigration', /Minister of Immigration/],
  ['{mpName}', /\{mpName\}/],
  ['{riding}', /\{riding\}/],
];

// Claims reworded variants kept inventing in trials. the original letter makes none of them, and a
// constituent should not send them under their own name.
export const FORBIDDEN_CLAIMS = [
  ['praise Teo beyond the original (acclaimed, renowned, model citizen)', /\b(critically )?acclaimed\b|\brenowned\b|model (citizen|immigrant)/i],
  ['describe Teo’s record (vetted, clean, safe, without incident, risk)', /\bvetted\b|without incident|\b(clean|spotless|safe)\b[^.]{0,30}\b(record|history|travel)|\b(high|low)[- ]risk\b|poses no (security )?risk/i],
  ['say information was requested (the original says none was provided)', /(additional|further) information (has been |was |being )?requested|request(ed)? for (any )?(additional|further) information|without any request/i],
  ['invent a job offer or family in Canada', /job offer|offer of employment|(family|relatives) (here |already )?in Canada/i],
  ['make claims about the sender (volunteer, donor, long-time supporter)', /long-?time supporter|I (volunteer|donate)|as a (volunteer|donor|sponsor)/i],
  ['use Markdown formatting', /\*[^*\n]+\*/],
];
const SIGNATURE = /\{firstName\} \{lastName\}\n\{street\}\n\{city\}, \{province\} \{postalCode\}\s*$/;

export function validateLetters(letters, { release = false } = {}) {
  const errors = [];
  if (!Array.isArray(letters) || letters.length === 0) {
    errors.push('Letter library must contain at least one entry');
    return errors;
  }

  const ids = new Set();
  letters.forEach((letter, index) => {
    const label = `Entry ${index + 1}`;
    if (!letter || typeof letter !== 'object') {
      errors.push(`${label} must be an object`);
      return;
    }
    if (typeof letter.id !== 'string' || !letter.id.trim()) errors.push(`${label} must have a non-blank id`);
    else if (ids.has(letter.id)) errors.push(`Duplicate id: ${letter.id}`);
    else ids.add(letter.id);
    if (typeof letter.subject !== 'string' || !letter.subject.trim()) errors.push(`${label} subject must not be blank`);
    if (typeof letter.body !== 'string' || !letter.body.trim()) errors.push(`${label} body must not be blank`);
    if (letter.status !== 'preview' && letter.status !== 'approved') errors.push(`${label} status must be preview or approved`);
    if (release && letter.status === 'preview') errors.push(`${label} is preview and cannot be released`);
    if (letter.ridings !== undefined && (!Array.isArray(letter.ridings) || letter.ridings.some((riding) => typeof riding !== 'string' || !riding.trim()))) {
      errors.push(`${label} ridings must be a list of riding names`);
    }
    if (release && typeof letter.body === 'string') {
      const text = `${letter.subject ?? ''}\n${letter.body}`;
      for (const [fact, pattern] of REQUIRED_FACTS) if (!pattern.test(text)) errors.push(`${label} (${letter.id}) is missing ${fact}`);
      for (const [claim, pattern] of FORBIDDEN_CLAIMS) if (pattern.test(text)) errors.push(`${label} (${letter.id}) must not ${claim}`);
      if (!SIGNATURE.test(letter.body)) errors.push(`${label} (${letter.id}) must end with the full signature and address tokens`);
    }

    for (const text of [letter.subject, letter.body]) {
      if (typeof text !== 'string') continue;
      for (const token of text.matchAll(/\{([^{}]+)\}/g)) {
        if (!SUPPORTED_TOKENS.has(token[1])) errors.push(`${label} contains unknown token: {${token[1]}}`);
      }
    }
  });
  return errors;
}

async function main() {
  const args = process.argv.slice(2);
  const release = args.includes('--release');
  const fileArg = args.find((arg) => arg !== '--release');
  const file = fileArg ? path.resolve(fileArg) : path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../server/letters.json');
  let letters;
  try {
    letters = JSON.parse(await readFile(file, 'utf8'));
  } catch (error) {
    console.error(`Unable to read ${file}: ${error.message}`);
    process.exitCode = 1;
    return;
  }
  const errors = validateLetters(letters, { release });
  if (errors.length) {
    for (const error of errors) console.error(`- ${error}`);
    process.exitCode = 1;
  } else {
    console.log(`Validated ${letters.length} letter${letters.length === 1 ? '' : 's'}${release ? ' for release' : ''}.`);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) await main();
