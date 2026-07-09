/**
 * api.ts — single choke point for every backend call. Prepends the
 * user-configured backend URL (lib/settings.ts) and always sends the API
 * token in the `Authorization` header — never in a query string or URL, so
 * it never ends up in browser history, proxy logs, or a Cloudflare Tunnel
 * access log.
 *
 * apiFetch()  — regular JSON request/response.
 * apiStream() — SSE endpoints (/api/sync/progress, /api/chat). Reads the
 *               fetch Response body as a stream instead of using
 *               EventSource, because EventSource cannot send custom headers
 *               (it has no way to carry a Bearer token) and only supports
 *               GET.
 */
import { getApiToken, getApiUrl } from "./settings";

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function buildUrl(path: string): string {
  if (/^https?:\/\//i.test(path)) return path;
  const base = getApiUrl();
  return `${base}${path.startsWith("/") ? "" : "/"}${path}`;
}

function buildHeaders(init?: HeadersInit, hasJsonBody = false): Headers {
  const headers = new Headers(init);
  const token = getApiToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (hasJsonBody && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return headers;
}

async function readErrorDetail(res: Response): Promise<string> {
  try {
    const text = await res.text();
    if (!text) return res.statusText || `HTTP ${res.status}`;
    try {
      const parsed = JSON.parse(text);
      if (parsed && typeof parsed.detail === "string") return parsed.detail;
      if (parsed && parsed.detail !== undefined) return JSON.stringify(parsed.detail);
      return text;
    } catch {
      return text;
    }
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

function isJsonBody(init: RequestInit | undefined): boolean {
  if (!init || init.body === undefined || init.body === null) return false;
  // FormData/Blob/URLSearchParams set their own Content-Type; only string
  // bodies from JSON.stringify(...) should get the default application/json.
  return typeof init.body === "string";
}

function networkError(): ApiError {
  return new ApiError(
    0,
    `Could not reach the backend at ${getApiUrl()}. Check that it is running and that the URL in Settings is correct.`
  );
}

/** JSON request/response. Throws ApiError on network failure or non-2xx status. */
export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const url = buildUrl(path);
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: buildHeaders(init.headers, isJsonBody(init)),
    });
  } catch {
    throw networkError();
  }

  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }

  if (res.status === 204) return undefined as T;
  const text = await res.text();
  if (!text) return undefined as T;
  return JSON.parse(text) as T;
}

type SSEHandler = (event: string, data: unknown) => void;

/**
 * Reads an SSE (text/event-stream) response fetched with credentials in the
 * Authorization header. Parses frames separated by a blank line (handles
 * both "\n\n" and "\r\n\r\n"), joins multiple `data:` lines per the SSE
 * spec, ignores `:`-prefixed comment/ping lines (sse_starlette's keepalive
 * ping is exactly this — a bare comment, no event/data), and JSON.parses
 * each frame's data before invoking onEvent.
 *
 * Resolves when the stream ends (server closes it, e.g. after a terminal
 * sync/chat event). Throws ApiError if the initial response is non-2xx or
 * unreachable. If `signal` is aborted, resolves quietly instead of throwing.
 */
export async function apiStream(
  path: string,
  init: RequestInit,
  onEvent: SSEHandler,
  signal?: AbortSignal
): Promise<void> {
  const url = buildUrl(path);
  let res: Response;
  try {
    res = await fetch(url, {
      ...init,
      headers: buildHeaders(init.headers, isJsonBody(init)),
      signal,
    });
  } catch (err) {
    if (signal?.aborted || (err instanceof DOMException && err.name === "AbortError")) return;
    throw networkError();
  }

  if (!res.ok) {
    throw new ApiError(res.status, await readErrorDetail(res));
  }
  if (!res.body) {
    throw new ApiError(res.status, "This browser does not support streaming responses.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const processFrame = (rawFrame: string) => {
    let eventName = "message";
    const dataLines: string[] = [];

    for (const line of rawFrame.split("\n")) {
      if (line === "" || line.startsWith(":")) continue; // blank / comment (incl. ping)
      const colonIdx = line.indexOf(":");
      const field = colonIdx === -1 ? line : line.slice(0, colonIdx);
      let value = colonIdx === -1 ? "" : line.slice(colonIdx + 1);
      if (value.startsWith(" ")) value = value.slice(1);

      if (field === "event") eventName = value;
      else if (field === "data") dataLines.push(value);
    }

    if (dataLines.length === 0) return; // comment-only frame (ping) or malformed
    const raw = dataLines.join("\n");
    let parsed: unknown = raw;
    try {
      parsed = JSON.parse(raw);
    } catch {
      // Non-JSON payload — hand back the raw string.
    }
    onEvent(eventName, parsed);
  };

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      buffer = buffer.replace(/\r\n/g, "\n"); // normalize CRLF -> LF for frame splitting

      let sepIndex: number;
      while ((sepIndex = buffer.indexOf("\n\n")) !== -1) {
        const frame = buffer.slice(0, sepIndex);
        buffer = buffer.slice(sepIndex + 2);
        if (frame) processFrame(frame);
      }
    }
    // Flush a trailing frame with no terminating blank line.
    const tail = buffer.replace(/\r\n/g, "\n").trim();
    if (tail) processFrame(tail);
  } catch (err) {
    if (signal?.aborted) return;
    throw err;
  } finally {
    reader.releaseLock();
  }
}
