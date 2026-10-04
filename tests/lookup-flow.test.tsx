import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';
import App from '../src/App';
import { lookupMp } from '../src/lib/lookup';

vi.mock('../src/lib/lookup', () => ({
  lookupMp: vi.fn(),
}));

const mockedLookup = vi.mocked(lookupMp);
const mp = { name: 'Sample Member', riding: 'Sample Riding', email: 'member@parl.gc.ca', profileUrl: 'https://www.ourcommons.ca/members/en/sample' };

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

function form() {
  return {
    firstName: screen.getByLabelText('First name'),
    lastName: screen.getByLabelText('Last name'),
    street: screen.getByLabelText('Street address'),
    city: screen.getByLabelText('City'),
    province: screen.getByLabelText('Province or territory'),
    postalCode: screen.getByLabelText('Postal code'),
  };
}

async function fillValidAddress() {
  const user = userEvent.setup();
  const fields = form();
  await user.type(fields.firstName, 'Ari');
  await user.type(fields.lastName, 'Lee');
  await user.type(fields.street, '10 Main St');
  await user.type(fields.city, 'Ottawa');
  await user.type(fields.province, 'ON');
  await user.type(fields.postalCode, 'K1A 0B1');
  return user;
}

describe('constituent lookup flow', () => {
  it('rejects malformed postal codes before calling lookup', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText('Postal code'), '12345');
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect(mockedLookup).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toMatch(/valid canadian postal code/i);
  });

  it('requires constituent details before looking up a postcode', async () => {
    const user = userEvent.setup();
    render(<App />);
    await user.type(screen.getByLabelText('Postal code'), 'K1A 0B1');
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect(mockedLookup).not.toHaveBeenCalled();
    expect(screen.getByRole('alert').textContent).toMatch(/complete all of your details/i);
  });

  it('announces loading and disables submit while lookup is pending', async () => {
    let resolve: (value: { status: 'found'; mp: typeof mp }) => void = () => {};
    mockedLookup.mockImplementation(() => new Promise((r) => { resolve = r; }));
    render(<App />);
    const user = await fillValidAddress();
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect(screen.getAllByText(/finding your mp/i).length).toBeGreaterThan(0);
    expect((screen.getByRole('button', { name: /finding your mp/i }) as HTMLButtonElement).disabled).toBe(true);
    resolve({ status: 'found', mp });
    await waitFor(() => expect(screen.getByText('Sample Member')).toBeTruthy());
  });

  it('shows a single MP with riding, email, and official profile link', async () => {
    mockedLookup.mockResolvedValue({ status: 'found', mp });
    render(<App />);
    const user = await fillValidAddress();
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect(await screen.findByText('Sample Member')).toBeTruthy();
    expect(screen.getByText('Sample Riding')).toBeTruthy();
    expect(screen.getByRole('link', { name: /official profile/i }).getAttribute('href')).toBe(mp.profileUrl);
    expect(screen.getByText(mp.email)).toBeTruthy();
  });

  it('requires an explicit choice when a postal code has two MPs', async () => {
    mockedLookup.mockResolvedValue({ status: 'multiple', mps: [mp, { ...mp, name: 'Second Member', email: 'second@parl.gc.ca' }] });
    render(<App />);
    const user = await fillValidAddress();
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect(await screen.findByText(/choose your mp/i)).toBeTruthy();
    expect((screen.getByRole('radio', { name: /sample member/i }) as HTMLInputElement).checked).toBe(false);
    expect((screen.getByRole('radio', { name: /second member/i }) as HTMLInputElement).checked).toBe(false);
    expect(screen.queryByRole('button', { name: /send email/i })).toBeNull();
    await user.click(screen.getByRole('radio', { name: /second member/i }));
    expect(screen.getByText('Second Member')).toBeTruthy();
  });

  it('keeps the form and offers retry plus manual search on unavailable lookup', async () => {
    mockedLookup.mockResolvedValue({ status: 'unavailable' });
    render(<App />);
    const user = await fillValidAddress();
    await user.click(screen.getByRole('button', { name: /find my mp/i }));
    expect((await screen.findByRole('alert')).textContent).toMatch(/temporarily unavailable/i);
    expect(screen.getByRole('button', { name: /try again/i })).toBeTruthy();
    expect(screen.getByRole('link', { name: /search the house of commons/i }).getAttribute('href')).toBe('https://www.ourcommons.ca/Members/en/search');
    expect((screen.getByLabelText('First name') as HTMLInputElement).value).toBe('Ari');
    expect((screen.getByLabelText('Postal code') as HTMLInputElement).value).toBe('K1A 0B1');
  });
});
