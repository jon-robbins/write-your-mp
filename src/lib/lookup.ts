import { getCampaignConfig } from '../config';

export interface Mp { name: string; riding: string; email: string; profileUrl?: string; }
export type LookupResult =
  | { status: 'found'; mp: Mp }
  | { status: 'multiple'; mps: Mp[] }
  | { status: 'not_found' | 'invalid' | 'unavailable' };

export async function lookupMp(postalCode: string): Promise<LookupResult> {
  try {
    const response = await fetch(getCampaignConfig().lookupUrl, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ postalCode }),
    });
    return await response.json() as LookupResult;
  } catch (_error) {
    return { status: 'unavailable' };
  }
}
