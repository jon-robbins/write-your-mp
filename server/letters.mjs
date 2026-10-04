import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

// Letters stay on the server so the page source never lists the whole library.
export function loadLetters(file = path.join(path.dirname(fileURLToPath(import.meta.url)), 'letters.json')) {
  return JSON.parse(readFileSync(file, 'utf8'));
}

// A riding with its own letters (e.g. Ottawa Centre, whose MP already made inquiries) gets only
// those; every other riding gets the general letters.
export function letterPool(letters, riding) {
  const own = letters.filter((letter) => Array.isArray(letter.ridings) && letter.ridings.includes(riding));
  return own.length > 0 ? own : letters.filter((letter) => !Array.isArray(letter.ridings));
}

export function pickLetter(letters, { riding, exclude, random = Math.random } = {}) {
  const pool = letterPool(letters, riding);
  if (pool.length === 0) return { letter: null, poolSize: 0 };
  const choices = pool.length > 1 ? pool.filter((letter) => letter.id !== exclude) : pool;
  const index = Math.min(Math.floor(Math.max(random(), 0) * choices.length), choices.length - 1);
  return { letter: choices[index], poolSize: pool.length };
}
