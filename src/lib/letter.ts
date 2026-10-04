import { getCampaignConfig } from '../config';

export interface Letter {
  id: string;
  subject: string;
  body: string;
}

export interface LetterResult {
  letter: Letter;
  poolSize: number;
}

// Only the riding leaves the browser; the visitor's name and address are merged in locally.
export async function fetchLetter(riding: string, exclude?: string): Promise<LetterResult | null> {
  const params = new URLSearchParams({ riding });
  if (exclude) params.set('exclude', exclude);
  try {
    const response = await fetch(`${getCampaignConfig().letterUrl}?${params}`, { cache: 'no-store' });
    if (!response.ok) return null;
    const { id, subject, body, poolSize } = await response.json();
    if (typeof id !== 'string' || typeof subject !== 'string' || typeof body !== 'string') return null;
    return { letter: { id, subject, body }, poolSize: Number(poolSize) || 1 };
  } catch {
    return null;
  }
}
