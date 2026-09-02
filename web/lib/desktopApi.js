/**
 * Desktop API bridge for pywebview.
 * All public methods on the Python Api class are available at
 * window.pywebview.api.<methodName>
 */

export const hasDesktopApi = () => Boolean(window.pywebview?.api);

/**
 * Call a method on the Python backend. Returns undefined if pywebview
 * is not available (browser preview mode).
 */
export async function callDesktop(method, ...args) {
  const api = window.pywebview?.api;
  if (!api?.[method]) return undefined;
  try {
    return await api[method](...args);
  } catch (error) {
    console.error(`Desktop API ${method} failed`, error);
    throw error;
  }
}

/**
 * Wait for pywebview to be ready, then invoke a callback.
 */
export function onDesktopReady(callback) {
  if (hasDesktopApi()) {
    callback();
  } else {
    window.addEventListener('pywebviewready', callback, { once: true });
  }
}
