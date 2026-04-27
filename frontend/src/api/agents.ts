// Client for the Customer Insight Agent SSE endpoint.
//
// We can't use axios for SSE (no streaming body in XHR). Use fetch + ReadableStream.
// Auth token comes from localStorage — same place axios interceptor reads it.

import { apiBase } from '../config/casdoor';

export type InsightEvent =
  | { type: 'run_created'; data: { run_id: number; customer_id: number } }
  | { type: 'run_started'; data: { run_id: number; customer_id: number; max_steps: number } }
  | { type: 'step_progress'; data: { done: number; total: number } }
  | { type: 'tool_call'; data: { name: string; args: any } }
  | { type: 'tool_result'; data: { name: string; preview: string } }
  | { type: 'tool_error'; data: { name: string; error: string } }
  | { type: 'thinking'; data: { text: string } }
  | { type: 'fact_recorded'; data: { id: number; category: string; content: string; source_url?: string; fingerprint: string } }
  | { type: 'fact_skipped_duplicate'; data: { category: string; content: string; fingerprint: string } }
  | { type: 'finishing'; data: { summary_preview: string } }
  | { type: 'done'; data: { summary: string | null; token_usage: any; steps_done: number } }
  | { type: 'error'; data: { message: string } };

export interface InsightRun {
  id: number;
  customer_id: number;
  status: 'running' | 'completed' | 'failed';
  started_at: string;
  completed_at?: string | null;
  steps_total: number;
  steps_done: number;
  error_message?: string | null;
  summary?: string | null;
  fact_count?: number;
  duration_ms?: number | null;
}

export interface InsightFact {
  id: number;
  category: string;
  content: string;
  source_url?: string | null;
  run_id: number;
  discovered_at: string;
}

function authHeader(): Record<string, string> {
  const t = localStorage.getItem('token') || sessionStorage.getItem('token');
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/**
 * Start a new insight run, streaming events to the callback.
 * Returns a cancel function.
 */
export function startInsightRun(
  customerId: number,
  onEvent: (ev: InsightEvent) => void,
  opts?: { onComplete?: () => void; onError?: (err: Error) => void },
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const resp = await fetch(`${apiBase}/api/customer/${customerId}/insight/run`, {
        method: 'POST',
        headers: { Accept: 'text/event-stream', ...authHeader() },
        signal: controller.signal,
      });
      if (!resp.ok || !resp.body) {
        const text = await resp.text().catch(() => '');
        throw new Error(`HTTP ${resp.status} ${text.slice(0, 200)}`);
      }

      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        // SSE frames separated by double newline
        let idx: number;
        while ((idx = buf.indexOf('\n\n')) !== -1) {
          const frame = buf.slice(0, idx);
          buf = buf.slice(idx + 2);
          const ev = parseFrame(frame);
          if (ev) onEvent(ev);
        }
      }
      opts?.onComplete?.();
    } catch (e: any) {
      if (e?.name !== 'AbortError') opts?.onError?.(e);
    }
  })();

  return () => controller.abort();
}

function parseFrame(raw: string): InsightEvent | null {
  let event = '';
  const dataParts: string[] = [];
  for (const line of raw.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim();
    else if (line.startsWith('data:')) dataParts.push(line.slice(5).trim());
  }
  if (!event) return null;
  try {
    const data = dataParts.length ? JSON.parse(dataParts.join('\n')) : {};
    return { type: event as InsightEvent['type'], data } as InsightEvent;
  } catch {
    return null;
  }
}

import { api } from './axios';

export async function fetchInsightRuns(customerId: number): Promise<InsightRun[]> {
  const { data } = await api.get(`/api/customer/${customerId}/insight/runs`);
  return data;
}

export async function fetchInsightFacts(customerId: number, category?: string): Promise<InsightFact[]> {
  const { data } = await api.get(`/api/customer/${customerId}/insight/facts`, {
    params: category ? { category } : {},
  });
  return data;
}

export async function fetchInsightRunFacts(customerId: number, runId: number): Promise<InsightFact[]> {
  const { data } = await api.get(`/api/customer/${customerId}/insight/runs/${runId}`);
  return (data as { facts: InsightFact[] }).facts ?? [];
}
