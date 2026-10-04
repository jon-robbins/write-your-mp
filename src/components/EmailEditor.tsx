import { useEffect, useRef, useState } from 'react';
import type { Draft } from '../lib/emailDraft';
import { toCopyText, toGmail, toMailto, toOutlook } from '../lib/emailDraft';

const COPIED_MS = 2000;

interface EmailEditorProps {
  draft: Draft;
  onNewDraft?: () => void;
}

export default function EmailEditor({ draft: initialDraft, onNewDraft }: EmailEditorProps) {
  const [draft, setDraft] = useState(initialDraft);
  const [copyError, setCopyError] = useState('');
  const [copied, setCopied] = useState(false);
  useEffect(() => {
    if (!copied) return undefined;
    const timer = setTimeout(() => setCopied(false), COPIED_MS);
    return () => clearTimeout(timer);
  }, [copied]);
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const sendRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!menuOpen) return undefined;
    const closeOutside = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape') return;
      setMenuOpen(false);
      sendRef.current?.focus();
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('keydown', closeOnEscape);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('keydown', closeOnEscape);
    };
  }, [menuOpen]);
  const closeMenu = () => setMenuOpen(false);
  const copyText = toCopyText(draft);
  const update = (field: 'subject' | 'body', value: string) => setDraft((current) => ({ ...current, [field]: value }));
  const copy = async () => {
    try {
      if (!navigator.clipboard?.writeText) throw new Error('Clipboard unavailable');
      await navigator.clipboard.writeText(copyText);
      setCopyError('');
      setCopied(true);
    } catch {
      setCopied(false);
      setCopyError('Copy is unavailable in this browser. Select and copy the text below manually.');
    }
  };
  return <div className="email-editor">
    <label>To<input aria-label="To" value={draft.to} readOnly /></label>
    {draft.cc && <p className="draft-meta"><strong>CC:</strong> {draft.cc}</p>}
    <label>Subject<input value={draft.subject} onChange={(event) => update('subject', event.target.value)} /></label>
    <label>Message<textarea value={draft.body} onChange={(event) => update('body', event.target.value)} rows={13} /></label>
    <p className="draft-guidance">Opening a draft does not send it. Review the message and send it from your own account.</p>
    <div className="draft-actions">
      <div className="send-menu" ref={menuRef}>
        <button ref={sendRef} className="card-button" type="button" aria-expanded={menuOpen} aria-controls="send-options" onClick={() => setMenuOpen((open) => !open)}>
          Send email <span className="send-caret" aria-hidden="true">▾</span>
        </button>
        {menuOpen && <ul id="send-options" className="send-options">
          <li><a href={toMailto(draft)} onClick={closeMenu}>Email app <span aria-hidden="true">→</span></a></li>
          <li><a href={toGmail(draft)} target="_blank" rel="noreferrer" onClick={closeMenu}>Gmail <span aria-hidden="true">↗</span></a></li>
          <li><a href={toOutlook(draft)} target="_blank" rel="noreferrer" onClick={closeMenu}>Outlook.com <span aria-hidden="true">↗</span></a></li>
          <li><button type="button" onClick={copy} aria-live="polite">{copied ? <>Copied! <span aria-hidden="true">✓</span></> : <>Copy text <span aria-hidden="true">⧉</span></>}</button></li>
        </ul>}
      </div>
      {onNewDraft && <button className="new-draft-button" type="button" onClick={onNewDraft}>
        <span className="new-draft-icon" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2.25" strokeLinecap="round" strokeLinejoin="round">
            <path d="M20 12a8 8 0 1 1-2.34-5.66" />
            <path d="M20 4v5h-5" />
          </svg>
        </span>
        Generate another draft
      </button>}
    </div>
    {copyError && <p className="copy-error" role="alert">{copyError}</p>}
    {copyError && <pre className="copy-fallback" aria-label="Copyable email text">{copyText}</pre>}
  </div>;
}
