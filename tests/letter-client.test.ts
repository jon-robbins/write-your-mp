import { afterEach, describe, expect, it, vi } from 'vitest';
import { fetchLetter } from '../src/lib/letter';

describe('fetchLetter', () => {
  afterEach(() => vi.restoreAllMocks());

  it('asks for one letter for the riding, excluding the current one, and sends no personal details', async () => {
    window.CAMPAIGN_CONFIG = { lookupUrl: '/x/api/lookup-mp', letterUrl: '/x/api/letter' };
    const fetchMock = vi.spyOn(window, 'fetch').mockResolvedValue(new Response(JSON.stringify({ id: 'a', subject: 'S', body: 'B', poolSize: 3 }), { status: 200 }));
    const result = await fetchLetter('Ottawa Centre', 'old');
    expect(fetchMock).toHaveBeenCalledWith('/x/api/letter?riding=Ottawa+Centre&exclude=old', { cache: 'no-store' });
    expect(result).toEqual({ letter: { id: 'a', subject: 'S', body: 'B' }, poolSize: 3 });
  });

  it('returns null when the server is unavailable', async () => {
    vi.spyOn(window, 'fetch').mockResolvedValue(new Response('{}', { status: 503 }));
    expect(await fetchLetter('Kanata')).toBeNull();
    vi.spyOn(window, 'fetch').mockRejectedValue(new Error('offline'));
    expect(await fetchLetter('Kanata')).toBeNull();
  });
});
