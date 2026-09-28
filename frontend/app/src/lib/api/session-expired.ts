/**
 * The API rejected a signed-in request (401): the session is over, e.g. the
 * token expired or was issued by another deployment. The auth provider signs
 * out, which sends the person to the login page, instead of every page showing
 * the error.
 */

type SessionExpiredListener = () => void;

const listeners: Set<SessionExpiredListener> = new Set();

export function notifySessionExpired() {
  listeners.forEach((listener) => listener());
}

export function subscribeToSessionExpired(
  listener: SessionExpiredListener,
): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}
