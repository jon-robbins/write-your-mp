import { describe, expect, it } from 'vitest';
import letters from '../server/letters.json';
import { buildDraft, toCopyText, toGmail, toMailto, toOutlook } from '../src/lib/emailDraft';

const constituent = { firstName: 'Ari', lastName: 'Lee', street: '10 Main St', city: 'Ottawa', province: 'ON', postalCode: 'K1A 0B1' };
const mp = { name: 'Sample Member', riding: 'Sample Riding', email: 'member@parl.gc.ca', profileUrl: 'https://example.test/member' };

describe('email drafts', () => {
  for (const variant of letters) it(`merges ${variant.id}`, () => {
    const draft = buildDraft(variant, constituent, mp);
    expect(draft.to).toBe(mp.email); expect(draft.cc).toBe('');
    expect(draft.subject + draft.body).toContain('Sample Member');
    expect(draft.subject + draft.body).toContain('Sample Riding');
    expect(draft.body).toContain('Ari Lee'); expect(draft.body).toContain('10 Main St');
    expect(draft.body).toContain('Ottawa, ON K1A 0B1');
    expect(draft.body).not.toMatch(/\{[^}]+\}|undefined/);
    expect(toCopyText(draft)).toContain(`To: ${mp.email}`);
    expect(new URL(toMailto(draft)).searchParams.get('body')).toBe(draft.body);
    expect(toMailto(draft)).not.toContain('+');
    const gmail = new URL(toGmail(draft));
    expect(gmail.searchParams.get('su')).toBe(draft.subject);
    expect(gmail.searchParams.get('body')).toBe(draft.body);
    const outlook = new URL(toOutlook(draft));
    expect(outlook.origin + outlook.pathname).toBe('https://outlook.live.com/mail/0/deeplink/compose');
    expect(outlook.searchParams.get('to')).toBe(mp.email);
    expect(outlook.searchParams.get('subject')).toBe(draft.subject);
    expect(outlook.searchParams.get('body')).toBe(draft.body);
  });
});
