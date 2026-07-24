import type { JobConfig } from '../types';

const API_BASE = import.meta.env.VITE_API_URL ?? '';

export interface TaxonomyResponse {
  packs: string[];
  control_classes: string[];
  taxonomy: Record<string, { violation_type: string; pack: string; severity: string; control_ids: string[]; label: string }>;
}

export interface JobEvent {
  stage: string;
  message: string;
  count?: number;
  total?: number;
  failures?: number;
  job_id?: string;
  run_id?: string;
}

export interface CopilotResponse {
  answer: string;
  evidence_log_ids: string[];
  citations: {
    violation_id: string;
    log_id: string;
    control_id: string;
    violation_type: string;
    severity: string;
    explanation: string;
  }[];
  grounding: string;
}

export async function fetchTaxonomy(): Promise<TaxonomyResponse> {
  const res = await fetch(`${API_BASE}/api/taxonomy`);
  if (!res.ok) throw new Error('Failed to load taxonomy');
  return res.json();
}

export async function startJob(config: JobConfig): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      packs: config.packs,
      control_classes: config.control_classes.length ? config.control_classes : null,
      scenario_mix: config.scenario_mix,
      n_logs: config.n_logs,
      industry: config.industry,
      use_seed_fallback: config.use_seed_fallback
    })
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Failed to start job');
  }
  return res.json();
}

export async function loadSeedDataset(): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/seed`, { method: 'POST' });
  if (!res.ok) throw new Error('Failed to load seed dataset');
  return res.json();
}

export function subscribeJobEvents(
  jobId: string,
  onEvent: (ev: JobEvent) => void,
  onDone: () => void
): () => void {
  const url = `${API_BASE}/api/jobs/${jobId}/events`;
  const es = new EventSource(url);

  es.onmessage = (msg) => {
    try {
      const ev = JSON.parse(msg.data) as JobEvent;
      onEvent(ev);
      if (ev.stage === 'complete' || ev.stage === 'completed' || ev.stage === 'failed' || ev.message === 'stream-end') {
        es.close();
        onDone();
      }
    } catch {
      /* ignore parse errors */
    }
  };

  es.onerror = () => {
    es.close();
    onDone();
  };

  return () => es.close();
}

export async function queryCopilot(query: string): Promise<CopilotResponse> {
  const res = await fetch(`${API_BASE}/api/copilot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query })
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Copilot query failed');
  }
  return res.json();
}

export function exportBundleUrl(): string {
  return `${API_BASE}/api/export.zip`;
}
