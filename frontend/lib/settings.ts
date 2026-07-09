/**
 * settings.ts — backend URL + API token, stored in localStorage so a
 * deployed (Vercel) frontend can be pointed at a fresh Cloudflare quick-tunnel
 * URL from any device without a rebuild. Falls back to
 * NEXT_PUBLIC_API_URL / NEXT_PUBLIC_API_TOKEN (baked in at build time), then
 * to hardcoded defaults. SSR-safe: every accessor guards `typeof window`.
 */

const API_URL_KEY = "gmr.apiUrl";
const API_TOKEN_KEY = "gmr.apiToken";

const DEFAULT_API_URL = "http://localhost:8000";

function isBrowser(): boolean {
  return typeof window !== "undefined";
}

function stripTrailingSlash(url: string): string {
  return url.replace(/\/+$/, "");
}

export function getApiUrl(): string {
  if (isBrowser()) {
    const stored = window.localStorage.getItem(API_URL_KEY);
    if (stored && stored.trim()) return stripTrailingSlash(stored.trim());
  }
  const envUrl = process.env.NEXT_PUBLIC_API_URL;
  if (envUrl && envUrl.trim()) return stripTrailingSlash(envUrl.trim());
  return DEFAULT_API_URL;
}

export function getApiToken(): string {
  if (isBrowser()) {
    const stored = window.localStorage.getItem(API_TOKEN_KEY);
    if (stored && stored.trim()) return stored.trim();
  }
  return (process.env.NEXT_PUBLIC_API_TOKEN ?? "").trim();
}

export function setApiUrl(url: string): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(API_URL_KEY, stripTrailingSlash(url.trim()));
}

export function setApiToken(token: string): void {
  if (!isBrowser()) return;
  window.localStorage.setItem(API_TOKEN_KEY, token.trim());
}
