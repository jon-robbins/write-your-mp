import { createHash } from 'node:crypto';
import express from 'express';
import rateLimit from 'express-rate-limit';
import { readFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { loadLetters, pickLetter } from './letters.mjs';
import { createLookupCache } from './lookupCache.mjs';
import { mapRepresent, normalizePostalCode } from './represent.mjs';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const dist = path.join(root, 'dist');
const REPRESENT_URL = 'https://represent.opennorth.ca/postcodes/';
// Represent often takes 3-5 seconds for a postal code it has not served recently.
const REPRESENT_TIMEOUT_MS = 10_000;
export const CAMPAIGN_PATH = '/campaign';
// Sites allowed to embed the tool in an iframe, e.g. FRAME_ANCESTORS="https://example.org https://www.example.org".
export function frameAncestors(origins = process.env.FRAME_ANCESTORS ?? '') {
  const allowed = origins.split(/[\s,]+/).filter((origin) => /^https:\/\/[a-z0-9.-]+(:\d+)?$/i.test(origin));
  return ["frame-ancestors 'self'", ...allowed].join(' ');
}
// OpenNorth allows this server 60 lookups a minute in all, so no one visitor may spend much of it.
const LOOKUPS_PER_MINUTE = 20;
const LETTERS_PER_MINUTE = 120;

function inlineScriptHashes(page) {
  return [...page.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)]
    .map(([, code]) => `'sha256-${createHash('sha256').update(code).digest('base64')}'`);
}

// The page runs only its own bundle plus the inline config it ships, and talks only to this server.
function contentSecurityPolicy(scriptHashes, frameAncestorsDirective) {
  return [
    "default-src 'self'",
    ["script-src 'self'", ...scriptHashes].join(' '),
    "style-src 'self' https://fonts.googleapis.com",
    'font-src https://fonts.gstatic.com',
    "img-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    frameAncestorsDirective,
  ].join('; ');
}

function perVisitorLimit(limit) {
  return rateLimit({
    windowMs: 60_000,
    limit,
    standardHeaders: 'draft-8',
    legacyHeaders: false,
    handler: (_request, response) => response.status(429).set('Cache-Control', 'no-store').json({ status: 'unavailable' }),
  });
}

export function createApp({ fetch: upstreamFetch = globalThis.fetch, fetchImpl, letters = loadLetters(), random = Math.random, lookupCache = createLookupCache(),
  lookupLimit = LOOKUPS_PER_MINUTE, letterLimit = LETTERS_PER_MINUTE, framing = frameAncestors() } = {}) {
  const representFetch = fetchImpl ?? upstreamFetch;
  const app = express();
  app.disable('x-powered-by');
  // Cloud Run's front end is the one proxy in front of the app; its X-Forwarded-For entry is the visitor's address.
  app.set('trust proxy', 1);
  app.use((_request, response, next) => {
    response.set({
      'Content-Security-Policy': contentSecurityPolicy([], framing),
      'X-Content-Type-Options': 'nosniff',
      'Referrer-Policy': 'strict-origin-when-cross-origin',
    });
    next();
  });
  app.use(express.json({ limit: '1kb' }));
  app.get('/', (_request, response) => response.redirect(`${CAMPAIGN_PATH}/`));
  app.get('/healthz', (_request, response) => response.sendStatus(200));
  app.post(`${CAMPAIGN_PATH}/api/lookup-mp`, perVisitorLimit(lookupLimit), async (request, response) => {
    response.set('Cache-Control', 'no-store');
    const postalCode = normalizePostalCode(request.body?.postalCode);
    if (!postalCode) return response.status(400).json({ status: 'invalid' });
    const cached = lookupCache.get(postalCode);
    if (cached) return response.status(200).json(cached);
    try {
      const upstream = await representFetch(`${REPRESENT_URL}${postalCode}/`, { signal: AbortSignal.timeout(REPRESENT_TIMEOUT_MS) });
      if (!upstream.ok) return response.status(503).json({ status: 'unavailable' });
      const result = mapRepresent(await upstream.json());
      lookupCache.set(postalCode, result);
      return response.status(200).json(result);
    } catch (_error) {
      return response.status(503).json({ status: 'unavailable' });
    }
  });
  app.get(`${CAMPAIGN_PATH}/api/letter`, perVisitorLimit(letterLimit), (request, response) => {
    response.set('Cache-Control', 'no-store');
    const text = (value) => (typeof value === 'string' ? value.slice(0, 120) : undefined);
    const { letter, poolSize } = pickLetter(letters, { riding: text(request.query.riding), exclude: text(request.query.exclude), random });
    if (!letter) return response.status(503).json({ status: 'unavailable' });
    return response.json({ id: letter.id, subject: letter.subject, body: letter.body, poolSize });
  });
  // Asset names are content-hashed, so they can be cached forever.
  app.use(`${CAMPAIGN_PATH}/assets`, express.static(path.join(dist, 'assets'), { immutable: true, maxAge: '1y' }));
  // Cloud Run builds stamp every file 1980-01-01, so a size+mtime ETag can match across deploys and
  // revalidate a stale page that points at deleted assets. Send the page body so Express tags it by
  // content hash instead, and never store it.
  app.get(`${CAMPAIGN_PATH}/`, async (_request, response) => {
    response.set('Cache-Control', 'no-store');
    let page = '<!doctype html><html><body><div id="root"></div></body></html>';
    try {
      page = await readFile(path.join(dist, 'index.html'), 'utf8');
    } catch {
      // dist is absent in tests and before the first build; the empty shell still mounts nothing.
    }
    response.set('Content-Security-Policy', contentSecurityPolicy(inlineScriptHashes(page), framing));
    response.type('html').send(page);
  });
  // Malformed or oversized request bodies get a short JSON answer, never a framework error page.
  app.use((error, _request, response, _next) => {
    const clientError = error?.status >= 400 && error.status < 500;
    response.status(clientError ? 400 : 500).set('Cache-Control', 'no-store').json({ status: clientError ? 'invalid' : 'unavailable' });
  });
  return app;
}

const app = createApp();
export { app };
