/**
 * settings.ts — API token storage. The backend serves this UI, so all API
 * calls are same-origin relative fetches in the built app; only the token is
 * user-configurable. During `npm run dev` (separate dev server on :3000) the
 * API base points at the backend directly — NODE_ENV is statically replaced
 * at build time, so the production bundle keeps the same-origin "" base.
 * SSR-safe: accessors guard `typeof window`.
 */

const API_TOKEN_KEY = "gmr.apiToken";

export function getApiUrl(): string {
  return process.env.NODE_ENV === "development" ? "http://localhost:8000" : "";
}

export function getApiToken(): string {
  if (typeof window === "undefined") return "";
  return (window.localStorage.getItem(API_TOKEN_KEY) ?? "").trim();
}

export function setApiToken(token: string): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(API_TOKEN_KEY, token.trim());
}
