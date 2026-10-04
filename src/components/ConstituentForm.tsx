import { useState } from 'react';
import type { ChangeEvent, FormEvent } from 'react';
import { lookupMp, type LookupResult, type Mp } from '../lib/lookup';
import MpResult from './MpResult';

export interface Constituent {
  firstName: string; lastName: string; street: string; city: string; province: string; postalCode: string;
}

interface ConstituentFormProps { onMpConfirmed?: (mp: Mp, constituent: Constituent) => void; }
const postalPattern = /^[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z]\s?\d[ABCEGHJ-NPRSTV-Z]\d$/i;
const manualSearchUrl = 'https://www.ourcommons.ca/Members/en/search';

export default function ConstituentForm({ onMpConfirmed }: ConstituentFormProps) {
  const [values, setValues] = useState<Constituent>({ firstName: '', lastName: '', street: '', city: '', province: '', postalCode: '' });
  const [result, setResult] = useState<LookupResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const update = (field: keyof Constituent) => (event: ChangeEvent<HTMLInputElement>) => setValues((current) => ({ ...current, [field]: event.target.value }));
  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setError(''); setResult(null);
    if (!postalPattern.test(values.postalCode.trim())) { setError('Please enter a valid Canadian postal code.'); return; }
    const missing = (Object.keys(values) as Array<keyof Constituent>).find((field) => !values[field].trim());
    if (missing) { setError('Please complete all of your details before finding your MP.'); return; }
    setLoading(true);
    const lookupResult = await lookupMp(values.postalCode);
    setLoading(false); setResult(lookupResult);
    if (lookupResult.status === 'found') onMpConfirmed?.(lookupResult.mp, values);
  };
  const select = (mp: Mp) => onMpConfirmed?.(mp, values);
  const failed = result?.status === 'not_found' || result?.status === 'unavailable';
  return <article className="campaign-card form-card" id="campaign-form">
    <p className="card-step">01 · Your details</p>
    <h2>Find your Member of Parliament</h2>
    <p className="card-intro">Enter your address so we can direct your message to the right representative.</p>
    <p className="address-privacy">Your address appears only in your draft signature and is never sent to the lookup server. Only your postal code is used to find your MP.</p>
    <form className="campaign-form" onSubmit={submit} noValidate>
      <div className="form-fields">
        {([['firstName', 'First name', 'given-name'], ['lastName', 'Last name', 'family-name'], ['street', 'Street address', 'street-address'], ['city', 'City', 'address-level2'], ['province', 'Province or territory', 'address-level1'], ['postalCode', 'Postal code', 'postal-code']] as const).map(([field, label, autocomplete]) => <label className={field === 'street' ? 'field-wide' : undefined} key={field}>{label}<input required name={field} value={values[field]} onChange={update(field)} autoComplete={autocomplete} /></label>)}
      </div>
      <button className="card-button" type="submit" disabled={loading}>{loading ? 'Finding your MP…' : 'Find my MP'} <span aria-hidden="true">→</span></button>
    </form>
    <div className="lookup-feedback" aria-live="polite">
      {loading && <p>Finding your MP…</p>}
      {error && <p role="alert">{error}</p>}
      {result?.status === 'found' && <MpResult mp={result.mp} onSelect={select} />}
      {result?.status === 'multiple' && <MpResult mps={result.mps} onSelect={select} />}
      {result?.status === 'not_found' && <p role="alert">We couldn’t find an MP for that postal code.</p>}
      {result?.status === 'unavailable' && <p role="alert">The lookup service is temporarily unavailable. Please try again or search manually.</p>}
      {failed && <p className="manual-search"><button type="button" onClick={() => { setResult(null); setError(''); }}>Try again</button> <a href={manualSearchUrl} target="_blank" rel="noreferrer">Search the House of Commons</a></p>}
    </div>
  </article>;
}
