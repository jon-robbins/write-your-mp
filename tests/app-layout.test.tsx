import { cleanup, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it } from 'vitest';
import App from '../src/App';

describe('campaign layout', () => {
  afterEach(cleanup);

  it('shows the campaign intro when opened directly', () => {
    render(<App embedded={false} />);
    expect(screen.getByRole('heading', { level: 1, name: /help teo castell find a home in canada/i })).toBeTruthy();
    expect(screen.getByText(/demo campaign/i)).toBeTruthy();
    expect(screen.queryByRole('banner')).toBeNull();
  });

  it('leaves the intro to the host page when embedded', () => {
    render(<App embedded />);
    expect(screen.queryByRole('heading', { level: 1 })).toBeNull();
    expect(screen.getByRole('heading', { name: /find your member of parliament/i })).toBeTruthy();
    expect(screen.queryByText(/client mock-up/i)).toBeNull();
  });
});
