/**
 * Casdoor SPA config. All values come from VITE_* env at build time.
 */
export const casdoor = {
  endpoint: (import.meta.env.VITE_CASDOOR_ENDPOINT || '').replace(/\/$/, ''),
  clientId: import.meta.env.VITE_CASDOOR_CLIENT_ID || '',
  org: import.meta.env.VITE_CASDOOR_ORG || 'operation',
  app: import.meta.env.VITE_CASDOOR_APP || 'sales',
  redirect: import.meta.env.VITE_CASDOOR_REDIRECT || `${window.location.origin}/auth/callback`,
};

export const apiBase = (import.meta.env.VITE_API_BASE || '').replace(/\/$/, '');

/** Build Casdoor authorize URL for the browser redirect flow. */
export function authorizeUrl(state: string): string {
  const p = new URLSearchParams({
    client_id: casdoor.clientId,
    response_type: 'code',
    redirect_uri: casdoor.redirect,
    scope: 'read profile email',
    state,
  });
  return `${casdoor.endpoint}/login/oauth/authorize?${p.toString()}`;
}

export function randomState(): string {
  const bytes = new Uint8Array(12);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
}
