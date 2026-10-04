import { afterEach, describe, expect, it, vi } from 'vitest';
import { lookupMp } from '../src/lib/lookup';

describe('lookupMp', () => {
  afterEach(() => vi.restoreAllMocks());

  it('posts only the postal code to the configured endpoint', async () => {
    window.CAMPAIGN_CONFIG = { lookupUrl: '/custom/api/lookup-mp', letterUrl: '/custom/api/letter' };
    const fetchMock = vi.spyOn(window, 'fetch').mockResolvedValue(new Response(JSON.stringify({ status: 'not_found' }), { status: 200 }));

    await lookupMp('K1A 0B1');

    expect(fetchMock).toHaveBeenCalledWith('/custom/api/lookup-mp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ postalCode: 'K1A 0B1' }),
    });
  });
});
