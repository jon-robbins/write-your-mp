export const HEIGHT_MESSAGE_TYPE = 'mp-letter:height';

export function isEmbedded(win: Window = window): boolean {
  try {
    return win.self !== win.top;
  } catch {
    return true;
  }
}

// Height is not sensitive, so any parent may read it; the parent page checks the sender's origin.
export function startHeightReporting(
  win: Window,
  target: HTMLElement,
  Observer: typeof ResizeObserver | undefined = globalThis.ResizeObserver,
): () => void {
  if (!isEmbedded(win)) return () => {};
  // Skip zero: before React renders, reporting it would collapse the parent's fallback height.
  const post = () => {
    const height = Math.ceil(target.scrollHeight);
    if (height > 0) win.parent.postMessage({ type: HEIGHT_MESSAGE_TYPE, height }, '*');
  };
  post();
  if (!Observer) return () => {};
  const observer = new Observer(post);
  observer.observe(target);
  return () => observer.disconnect();
}
