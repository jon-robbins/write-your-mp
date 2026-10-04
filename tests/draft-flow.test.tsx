import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { lookupMp } from '../src/lib/lookup';
import { fetchLetter } from '../src/lib/letter';

vi.mock('../src/lib/lookup', () => ({ lookupMp: vi.fn() }));
vi.mock('../src/lib/letter', () => ({ fetchLetter: vi.fn() }));

const mockedLookup = vi.mocked(lookupMp);
const mockedLetter = vi.mocked(fetchLetter);
const mp = { name: 'Sample Member', riding: 'Sample Riding', email: 'member@parl.gc.ca', profileUrl: 'https://www.ourcommons.ca/members/en/sample' };
const first = { id: 'v1', subject: 'Application delay for Teo Castell', body: 'Dear {mpName},\n\nI live in {riding}.\n\nSincerely,\n\n{firstName} {lastName}\n{street}\n{city}, {province} {postalCode}' };
const second = { id: 'v2', subject: 'Please help Teo Castell', body: 'Dear {mpName},\n\nSecond letter from {riding}.\n\nSincerely,\n\n{firstName} {lastName}\n{street}\n{city}, {province} {postalCode}' };

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.resetAllMocks();
});

async function completeLookup(poolSize = 2) {
  mockedLookup.mockResolvedValue({ status: 'found', mp });
  mockedLetter.mockResolvedValueOnce({ letter: first, poolSize }).mockResolvedValueOnce({ letter: second, poolSize });
  const user = userEvent.setup();
  const view = render(<App embedded />);
  await user.type(screen.getByLabelText('First name'), 'Ari');
  await user.type(screen.getByLabelText('Last name'), 'Lee');
  await user.type(screen.getByLabelText('Street address'), '10 Main St');
  await user.type(screen.getByLabelText('City'), 'Ottawa');
  await user.type(screen.getByLabelText('Province or territory'), 'ON');
  await user.type(screen.getByLabelText('Postal code'), 'K1A 0B1');
  await user.click(screen.getByRole('button', { name: /find my mp/i }));
  await screen.findByLabelText('Subject');
  return { user, rerender: view.rerender };
}

describe('editable draft flow', () => {
  it('fetches a letter for the MP riding and fills in the MP, riding, and visitor locally', async () => {
    await completeLookup();
    expect(mockedLetter).toHaveBeenCalledWith('Sample Riding', undefined);
    expect((screen.getByLabelText('Subject') as HTMLInputElement).value).toBe('Application delay for Teo Castell');
    const body = (screen.getByLabelText('Message') as HTMLTextAreaElement).value;
    expect(body).toContain('Dear Sample Member');
    expect(body).toContain('I live in Sample Riding.');
    expect(body).toContain('Ari Lee\n10 Main St\nOttawa, ON K1A 0B1');
    expect((screen.getByLabelText('To') as HTMLInputElement).value).toBe('member@parl.gc.ca');
    expect(screen.queryByText(/client mock-up/i)).toBeNull();
  });

  it('keeps edits in handoff URLs and copied text', async () => {
    const { user } = await completeLookup();
    const subject = screen.getByLabelText('Subject');
    const message = screen.getByLabelText('Message');
    await user.clear(subject);
    await user.type(subject, 'A changed subject');
    await user.click(message);
    await user.type(message, '\nA changed closing.');
    await user.click(screen.getByRole('button', { name: /send email/i }));
    const mailto = screen.getByRole('link', { name: /email app/i });
    const gmail = screen.getByRole('link', { name: /gmail/i });
    const outlook = screen.getByRole('link', { name: /outlook\.com/i });
    expect(new URL(outlook.getAttribute('href')!).searchParams.get('body')).toContain('A changed closing.');
    expect(new URL(mailto.getAttribute('href')!).searchParams.get('subject')).toBe('A changed subject');
    expect(new URL(mailto.getAttribute('href')!).searchParams.get('body')).toContain('A changed closing.');
    expect(new URL(gmail.getAttribute('href')!).searchParams.get('body')).toContain('A changed closing.');
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } });
    await user.click(screen.getByRole('button', { name: /copy text/i }));
    expect(writeText).toHaveBeenCalledWith(expect.stringContaining('Subject: A changed subject'));
    expect(screen.getByRole('button', { name: /copied!/i })).toBeTruthy();
    await waitFor(() => expect(screen.getByRole('button', { name: /copy text/i })).toBeTruthy(), { timeout: 3000 });
  });

  it('keeps the ways to send behind one Send email menu', async () => {
    const { user } = await completeLookup();
    const send = screen.getByRole('button', { name: /send email/i });
    expect(send.getAttribute('aria-expanded')).toBe('false');
    expect(screen.queryByRole('link', { name: /gmail/i })).toBeNull();
    await user.click(send);
    expect(send.getAttribute('aria-expanded')).toBe('true');
    expect(within(document.getElementById('send-options')!).getAllByRole('link').map((link) => link.textContent?.replace(/[↗→]/g, '').trim())).toEqual(['Email app', 'Gmail', 'Outlook.com']);
    await user.keyboard('{Escape}');
    expect(screen.queryByRole('link', { name: /gmail/i })).toBeNull();
    expect(document.activeElement).toBe(send);
    await user.click(send);
    await user.click(screen.getByLabelText('Subject'));
    expect(screen.queryByRole('link', { name: /gmail/i })).toBeNull();
  });

  it('preserves edited content across a React rerender', async () => {
    const { user, rerender } = await completeLookup();
    const subject = screen.getByLabelText('Subject');
    await user.clear(subject);
    await user.type(subject, 'Reviewed subject');
    rerender(<App embedded />);
    expect((screen.getByLabelText('Subject') as HTMLInputElement).value).toBe('Reviewed subject');
  });

  it('Generate another draft fetches a different letter, excluding the current one', async () => {
    const { user } = await completeLookup();
    await user.click(screen.getByRole('button', { name: /generate another draft/i }));
    await waitFor(() => expect((screen.getByLabelText('Subject') as HTMLInputElement).value).toBe('Please help Teo Castell'));
    expect(mockedLetter).toHaveBeenLastCalledWith('Sample Riding', 'v1');
  });

  it('hides Generate another draft when the riding has only one letter', async () => {
    await completeLookup(1);
    expect(screen.queryByRole('button', { name: /generate another draft/i })).toBeNull();
  });

  it('offers a retry when the letter cannot be loaded', async () => {
    mockedLookup.mockResolvedValue({ status: 'found', mp });
    mockedLetter.mockResolvedValueOnce(null).mockResolvedValueOnce({ letter: first, poolSize: 1 });
    const user = userEvent.setup();
    render(<App embedded />);
    for (const [label, value] of [['First name', 'Ari'], ['Last name', 'Lee'], ['Street address', '10 Main St'], ['City', 'Ottawa'], ['Province or territory', 'ON'], ['Postal code', 'K1A 0B1']]) await user.type(screen.getByLabelText(label), value);
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/couldn.t load the letter/i);
    await user.click(screen.getByRole('button', { name: /try again/i }));
    expect(await screen.findByLabelText('Subject')).toBeTruthy();
  });

  it('shows selectable fallback text when clipboard access is unavailable', async () => {
    const { user } = await completeLookup();
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: undefined });
    await user.click(screen.getByRole('button', { name: /send email/i }));
    await user.click(screen.getByRole('button', { name: /copy text/i }));
    expect(screen.getByRole('alert').textContent).toMatch(/copy is unavailable/i);
    expect(screen.getByLabelText('Copyable email text').textContent).toContain('To: member@parl.gc.ca');
  });
});
