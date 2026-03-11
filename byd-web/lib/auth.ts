export interface AuthUser {
  id: string;
  name: string;
  email: string;
}

const SESSION_KEY = "promptdash_session_user";
const TOKEN_KEY = "promptdash_access_token";

function normalizeEmail(email: string): string {
  return email.trim().toLowerCase();
}

export function buildUserId(email: string): string {
  return normalizeEmail(email).replace(/[^a-z0-9]+/g, "-");
}

export function loadCurrentUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(SESSION_KEY);
  if (!raw) return null;

  try {
    const parsed = JSON.parse(raw) as AuthUser;
    if (!parsed?.id || !parsed?.email) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function saveSession(user: AuthUser, accessToken: string): AuthUser {
  if (typeof window !== "undefined") {
    window.localStorage.setItem(SESSION_KEY, JSON.stringify(user));
    window.localStorage.setItem(TOKEN_KEY, accessToken);
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
}
