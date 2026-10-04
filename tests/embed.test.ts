import { describe, expect, it, vi } from 'vitest';
import { HEIGHT_MESSAGE_TYPE, isEmbedded, startHeightReporting } from '../src/lib/embed';

function fakeWindow({ framed }: { framed: boolean }) {
  const parent = { postMessage: vi.fn() };
  const win = { parent } as unknown as Window & { self: unknown; top: unknown };
  win.self = win;
  win.top = framed ? parent : win;
  return { win, parent };
}

class FakeObserver {
  static instances: FakeObserver[] = [];
  observed: Element[] = [];
  constructor(public callback: () => void) { FakeObserver.instances.push(this); }
  observe(target: Element) { this.observed.push(target); }
  disconnect() { this.observed = []; }
}

describe('embed helpers', () => {
  it('detects whether the page is framed', () => {
    expect(isEmbedded(fakeWindow({ framed: true }).win)).toBe(true);
    expect(isEmbedded(fakeWindow({ framed: false }).win)).toBe(false);
  });

  it('treats a cross-origin access error as framed', () => {
    const win = { get top() { throw new Error('cross-origin'); } } as unknown as Window;
    expect(isEmbedded(win)).toBe(true);
  });

  it('posts the content height to the parent now and on every resize', () => {
    const { win, parent } = fakeWindow({ framed: true });
    const target = { scrollHeight: 812.4 } as unknown as HTMLElement;
    const stop = startHeightReporting(win, target, FakeObserver as unknown as typeof ResizeObserver);
    expect(parent.postMessage).toHaveBeenLastCalledWith({ type: HEIGHT_MESSAGE_TYPE, height: 813 }, '*');
    (target as { scrollHeight: number }).scrollHeight = 1500;
    FakeObserver.instances.at(-1)!.callback();
    expect(parent.postMessage).toHaveBeenLastCalledWith({ type: HEIGHT_MESSAGE_TYPE, height: 1500 }, '*');
    stop();
    expect(FakeObserver.instances.at(-1)!.observed).toEqual([]);
  });

  it('never reports a zero height before the app has rendered', () => {
    const { win, parent } = fakeWindow({ framed: true });
    const target = { scrollHeight: 0 } as unknown as HTMLElement;
    startHeightReporting(win, target, FakeObserver as unknown as typeof ResizeObserver);
    expect(parent.postMessage).not.toHaveBeenCalled();
    (target as { scrollHeight: number }).scrollHeight = 900;
    FakeObserver.instances.at(-1)!.callback();
    expect(parent.postMessage).toHaveBeenCalledWith({ type: HEIGHT_MESSAGE_TYPE, height: 900 }, '*');
  });

  it('does nothing when the page is not framed', () => {
    const { win, parent } = fakeWindow({ framed: false });
    startHeightReporting(win, { scrollHeight: 100 } as unknown as HTMLElement, FakeObserver as unknown as typeof ResizeObserver);
    expect(parent.postMessage).not.toHaveBeenCalled();
  });
});
