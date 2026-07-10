/**
 * types.ts — TypeScript mirrors of backend/app/models.py request/response
 * shapes, plus the SSE event payloads defined in backend/app/sync_manager.py
 * (sync progress) and backend/app/agent/engine.py (chat, used by Phase 5).
 *
 * Keep these in lockstep with the backend Pydantic models — this file is the
 * single source of truth for what the frontend believes the API returns.
 */

// ── Status ───────────────────────────────────────────────────────────────────

export interface GmailStatus {
  connected: boolean;
  email: string;
}

export interface OllamaStatus {
  available: boolean;
  model: string;
  message: string;
}

export interface IndexStatus {
  count: number;
}

export interface StatusResponse {
  gmail: GmailStatus;
  ollama: OllamaStatus;
  index: IndexStatus;
}

// ── Gmail ────────────────────────────────────────────────────────────────────

export interface ConnectResponse {
  connected: boolean;
  email: string;
  needs_desktop_auth: boolean;
  /** Web-flow consent URL; the frontend opens it in a new tab. */
  auth_url: string;
}

export interface LabelOut {
  id: string;
  name: string;
  type: string;
}

// ── Sync ─────────────────────────────────────────────────────────────────────

export interface SyncStartRequest {
  max_emails: number;
  query: string;
  categories: string[];
}

export interface SyncStartResponse {
  job_id: string;
}

export type SyncPhase =
  | "idle"
  | "listing"
  | "fetching"
  | "embedding"
  | "done"
  | "error"
  | "cancelled";

/** sync_manager.py event schema, JSON-encoded as the "progress" SSE event's data. */
export interface SyncProgressEvent {
  job_id: string | null;
  phase: SyncPhase;
  fetched: number;
  embedded: number;
  total: number;
  added: number;
  message: string | null;
}

export const SYNC_TERMINAL_PHASES: ReadonlySet<SyncPhase> = new Set(["done", "error", "cancelled"]);

// ── Emails / stats ───────────────────────────────────────────────────────────

export interface EmailItem {
  id: string;
  subject: string;
  sender: string;
  recipient: string;
  date: string;
  snippet: string;
  labels: string[];
}

export interface EmailListResponse {
  total: number;
  items: EmailItem[];
}

export type EmailSortField = "date" | "sender" | "subject";
export type SortOrder = "asc" | "desc";

export interface StatsResponse {
  total_indexed: number;
  unique_senders: number;
  top_senders: [string, number][];
}

// ── Chat / agent (Phase 5) ────────────────────────────────────────────────────

export type ChatRole = "user" | "assistant";

export interface ChatMessage {
  role: ChatRole;
  content: string;
}

export interface ChatRequest {
  messages: ChatMessage[];
  confirm_token?: string | null;
  cancelled?: boolean;
}

// ── Routines ────────────────────────────────────────────────────────────────

export interface RoutineLastRun {
  at: string;
  trigger: "schedule" | "manual";
  scanned: number;
  labeled: number;
  skipped: number;
  errors: string[];
  duration_seconds: number;
}

export interface GenericRoutineStatus {
  enabled: boolean;
  interval_minutes: number;
  running: boolean;
  last_run: RoutineLastRun | null;
}

// engine.py event contract: (event_name, data) pairs, mapped 1:1 onto SSE frames.
export interface ChatTokenEvent {
  text: string;
}

export interface ChatToolCallEvent {
  name: string;
  arguments: Record<string, unknown>;
}

export interface ChatToolResultEvent {
  name: string;
  summary: string;
}

/** One row of tools.py's `_preview_item()` — id/subject/sender/date, no snippet. */
export interface ChatPreviewItem {
  id?: string;
  subject?: string;
  sender?: string;
  date?: string;
}

export interface ChatConfirmEvent {
  confirm_token: string;
  action: string;
  description: string;
  count: number;
  preview: ChatPreviewItem[];
}

export type ChatFinishReason = "stop" | "awaiting_confirmation";

export interface ChatDoneEvent {
  finish_reason: ChatFinishReason;
}

export interface ChatErrorEvent {
  message: string;
}
