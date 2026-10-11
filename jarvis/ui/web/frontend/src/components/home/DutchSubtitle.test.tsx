import { cleanup, render, screen, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { DutchSubtitle } from './DutchSubtitle';

class VisibleObserver {
  constructor(private callback: IntersectionObserverCallback) {}
  observe() { this.callback([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver); }
  disconnect() {}
}
vi.stubGlobal('IntersectionObserver', VisibleObserver);
afterEach(() => { cleanup(); vi.restoreAllMocks(); });
it('does not translate streaming fragments or show English while pending', () => {
  const fetcher = vi.spyOn(globalThis, 'fetch');
  render(<DutchSubtitle text="Live English fragment" live />);
  expect(screen.queryByText('Live English fragment')).toBeNull();
  expect(fetcher).not.toHaveBeenCalled();
});
it('renders Dutch and deduplicates identical completed text', async () => {
  const fetcher = vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response(JSON.stringify({text:'Het is zonnig.', language:'nl'})));
  const first = render(<DutchSubtitle text="It is sunny." live={false} />);
  await screen.findByText('Het is zonnig.');
  first.unmount();
  render(<DutchSubtitle text="It is sunny." live={false} />);
  await screen.findByText('Het is zonnig.');
  expect(fetcher).toHaveBeenCalledTimes(1);
});
it('keeps the original answer visible with an explicit failure label', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('', {status:503}));
  render(<DutchSubtitle text="Original unavailable translation" live={false} />);
  await waitFor(() => expect(screen.getByText('Vertaling niet beschikbaar · Engelse tekst')).toBeTruthy());
  expect(screen.getByText('Original unavailable translation')).toBeTruthy();
});
