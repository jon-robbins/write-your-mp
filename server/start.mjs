import { createApp } from './index.mjs';
import { demoRepresentFetch } from './demoRepresent.mjs';

const port = Number(process.env.PORT || 8080);
const demo = process.argv.includes('--demo') || process.env.DEMO_LOOKUP === '1';
const app = createApp(demo ? { fetch: demoRepresentFetch } : {});
app.listen(port, () => {
  console.log(`Letter tool listening on http://localhost:${port}/campaign/${demo ? ' (demo MPs, no OpenNorth calls)' : ''}`);
});
