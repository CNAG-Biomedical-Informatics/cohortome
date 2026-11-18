import { createRoot } from 'react-dom/client';
import { flushSync } from 'react-dom';

// One owner per host, including hosts reused for notices and dashboard views.
const roots = new WeakMap();
export function renderSupplemental(host, content) {
  if (!host) return;
  let root = roots.get(host);
  if (!root) {
    root = createRoot(host);
    roots.set(host, root);
  }
  flushSync(() => root.render(content));
}
export function resetSupplementalView(host) {
  const root = host && roots.get(host);
  if (root) {
    root.unmount();
    roots.delete(host);
  }
}
