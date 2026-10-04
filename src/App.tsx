import { useState } from 'react';
import ConstituentForm from './components/ConstituentForm';
import type { Constituent } from './components/ConstituentForm';
import type { Mp } from './lib/lookup';
import { fetchLetter } from './lib/letter';
import { buildDraft, type Draft } from './lib/emailDraft';
import { isEmbedded } from './lib/embed';
import EmailEditor from './components/EmailEditor';

type DraftState =
  | { status: 'idle' }
  | { status: 'loading' }
  | { status: 'error' }
  | { status: 'ready'; draft: Draft; letterId: string; poolSize: number; version: number };

export default function App({ embedded = isEmbedded() }: { embedded?: boolean }) {
  const [confirmed, setConfirmed] = useState<{ mp: Mp; constituent: Constituent } | null>(null);
  const [state, setState] = useState<DraftState>({ status: 'idle' });

  const loadDraft = async (mp: Mp, constituent: Constituent, exclude?: string) => {
    const previousVersion = state.status === 'ready' ? state.version : 0;
    setState({ status: 'loading' });
    const result = await fetchLetter(mp.riding, exclude);
    if (!result) return setState({ status: 'error' });
    setState({ status: 'ready', draft: buildDraft(result.letter, constituent, mp), letterId: result.letter.id, poolSize: result.poolSize, version: previousVersion + 1 });
  };
  const chooseDraft = (mp: Mp, constituent: Constituent) => {
    setConfirmed({ mp, constituent });
    void loadDraft(mp, constituent);
  };
  const retry = () => { if (confirmed) void loadDraft(confirmed.mp, confirmed.constituent); };
  const newDraft = () => {
    if (confirmed && state.status === 'ready') void loadDraft(confirmed.mp, confirmed.constituent, state.letterId);
  };

  return <main id="campaign-main" className={`campaign-page${embedded ? ' is-embedded' : ''}`}>
    {!embedded && <section className="campaign-hero" aria-labelledby="campaign-title">
      <p className="campaign-kicker">Northbridge Newcomer Alliance · MP outreach campaign</p>
      <h1 id="campaign-title">Help Teo Castell find a home in Canada</h1>
      <p className="campaign-intro">Teo Castell is stateless: no passport, no citizenship anywhere. His Canadian sponsors are ready, but his application has been stuck for 11 months. Ask your MP to help move it forward. We’ll draft the letter; you review it and send it from your own email.</p>
      <p className="campaign-mockup-notice">Demo campaign: every person and organization named here is fictional.</p>
    </section>}

    <section className="campaign-cards" aria-label="Campaign message steps">
      <ConstituentForm onMpConfirmed={chooseDraft} />

      <article className="campaign-card draft-card" aria-labelledby="draft-title">
        <p className="card-step">02 · Your message</p>
        <h2 id="draft-title">Make it personal</h2>
        <p className="card-intro">Your draft will appear here once we find your MP. You’ll have a chance to review and edit everything before sending.</p>
        <div className="draft-preview" aria-label="Message draft preview" aria-live="polite">
          <p className="draft-label">Preview</p>
          {state.status === 'idle' && <p className="draft-placeholder">Your message will be ready to review here.</p>}
          {state.status === 'loading' && <p className="draft-placeholder">Preparing your letter…</p>}
          {state.status === 'error' && <div className="manual-search"><p role="alert">We couldn’t load the letter. Please try again.</p><button type="button" onClick={retry}>Try again</button></div>}
          {state.status === 'ready' && <EmailEditor key={state.version} draft={state.draft} onNewDraft={state.poolSize > 1 ? newDraft : undefined} />}
        </div>
      </article>
    </section>

    <p className="campaign-notice">Your name and address stay in your browser and appear only in your draft. Only your postal code is sent to OpenNorth’s Represent service to look up your MP, and only your riding name is used to choose a letter. This tool is not operated by the Government of Canada.</p>
  </main>;
}
