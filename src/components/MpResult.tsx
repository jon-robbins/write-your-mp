import { useState } from 'react';
import type { Mp } from '../lib/lookup';

interface MpResultProps {
  mp?: Mp;
  mps?: Mp[];
  onSelect: (mp: Mp) => void;
}

export default function MpResult({ mp, mps, onSelect }: MpResultProps) {
  const [selected, setSelected] = useState<string | null>(null);
  const choices = mps ?? (mp ? [mp] : []);
  const multiple = choices.length > 1;
  const choose = (candidate: Mp) => {
    setSelected(candidate.email);
    onSelect(candidate);
  };
  return <section className="mp-result" aria-live="polite" aria-labelledby="mp-result-title">
    <h3 id="mp-result-title">{multiple ? 'Choose your MP' : 'Your Member of Parliament'}</h3>
    {multiple && <p>Postal codes can cross riding boundaries. Verify your riding, then choose the right representative.</p>}
    <div className="mp-choices">
      {choices.map((candidate) => <label className="mp-choice" key={candidate.email}>
        {multiple && <input type="radio" name="mp-choice" value={candidate.email} checked={selected === candidate.email} onChange={() => choose(candidate)} />}
        <span><strong>{candidate.name}</strong><span>{candidate.riding}</span>{candidate.profileUrl && <a href={candidate.profileUrl} target="_blank" rel="noreferrer">Official profile</a>}<a href={`mailto:${candidate.email}`}>{candidate.email}</a></span>
      </label>)}
    </div>
  </section>;
}
