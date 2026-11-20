export interface AuthUser {
  id: string;
  name: string;
  email: string;
}

const SESSION_KEY = "promptdash_session_user";
const TOKEN_KEY = "promptdash_access_token";

/* The session lives in localStorage, which React cannot see. It is read through
   `useSyncExternalStore` rather than an effect, so a component renders with the
   right session on its first client pass instead of flipping state afterwards.
   That needs two things from this module: a snapshot that is referentially
   stable while the stored string is unchanged (otherwise React re-renders
   forever), and a subscribe that fires when the session changes. */

const SESSION_EVENT = "promptdash:session";

let cachedRaw: string | null = null;
let cachedUser: AuthUser | null = null;

function parseUser(raw: string): AuthUser | null {
  try {
    const parsed = JSON.parse(raw) as AuthUser;
    if (!parsed?.id || !parsed?.email) return null;
    return parsed;
  } catch {
    return null;
  }
}

function announce(): void {
  window.dispatchEvent(new Event(SESSION_EVENT));
}

/** Subscribe to session changes: this tab via `announce`, other tabs via `storage`. */
export function subscribeToSession(onChange: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const onStorage = (event: StorageEvent) => {
    if (event.key === null || event.key === SESSION_KEY) onChange();
  };
  window.addEventListener(SESSION_EVENT, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(SESSION_EVENT, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

/** The server snapshot: there is no session during SSR, ever. */
export function noSession(): null {
  return null;
}

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function buildUserId(email: string): string {
  return normalizeEmail(email).replace(/[^a-z0-9]+/g, "-");
}

export function loadCurrentUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (raw !== cachedRaw) {
    cachedRaw = raw;
    cachedUser = raw ? parseUser(raw) : null;
  }
  return cachedUser;
}

export function saveSession(user: AuthUser, accessToken: string): AuthUser {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    window.localStorage.setItem(TOKEN_KEY, accessToken);
    announce();
  }
  return user;
}

export function getAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(TOKEN_KEY);
}

export function logoutUser(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(SESSION_KEY);
  window.localStorage.removeItem(TOKEN_KEY);
  announce();
}
