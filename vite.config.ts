import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';

export default defineConfig({
  base: './',
  plugins: [react()],
  // `npm run dev` serves the page with hot reload; API calls go to the Express server from `npm run dev:api`.
  server: { proxy: { '/campaign/api': 'http://localhost:8080' } },
  // Server and script tests (*.test.mjs) run under node --test; vitest covers the browser code.
  test: { environment: 'jsdom', include: ['tests/**/*.test.{ts,tsx}'] },
});
