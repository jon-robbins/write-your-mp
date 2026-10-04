import type { Letter } from './letter';

export interface Constituent {
  firstName: string;
  lastName: string;
  street: string;
  city: string;
  province: string;
  postalCode: string;
}

export interface Mp {
  name: string;
  riding: string;
  email: string;
  profileUrl?: string;
}

export interface Draft {
  to: string;
  cc: string;
  subject: string;
  body: string;
}

export function buildDraft(variant: Letter, constituent: Constituent, mp: Mp): Draft {
  const values: Record<string, string> = {
    mpName: mp.name,
    riding: mp.riding,
    firstName: constituent.firstName,
    lastName: constituent.lastName,
    street: constituent.street,
    city: constituent.city,
    province: constituent.province,
    postalCode: constituent.postalCode,
  };
  const merge = (text: string) => text.replace(/\{(mpName|riding|firstName|lastName|street|city|province|postalCode)\}/g, (_, token) => values[token]);
  return { to: mp.email, cc: '', subject: merge(variant.subject), body: merge(variant.body) };
}

function encodedQuery(entries: Array<[string, string]>) {
  return entries.filter(([, value]) => value).map(([key, value]) => `${encodeURIComponent(key)}=${encodeURIComponent(value)}`).join('&');
}

export function toMailto(draft: Draft): string {
  return `mailto:${encodeURIComponent(draft.to)}?${encodedQuery([['subject', draft.subject], ['body', draft.body], ['cc', draft.cc]])}`;
}

export function toGmail(draft: Draft): string {
  return `https://mail.google.com/mail/?view=cm&fs=1&${encodedQuery([['to', draft.to], ['su', draft.subject], ['body', draft.body], ['cc', draft.cc]])}`;
}

export function toOutlook(draft: Draft): string {
  return `https://outlook.live.com/mail/0/deeplink/compose?${encodedQuery([['to', draft.to], ['subject', draft.subject], ['body', draft.body], ['cc', draft.cc]])}`;
}

export function toCopyText(draft: Draft): string {
  return `To: ${draft.to}\n${draft.cc ? `CC: ${draft.cc}\n` : ''}Subject: ${draft.subject}\n\n${draft.body}`;
}
