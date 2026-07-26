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
  // Present on "stage_update" events — a structured, live-updating parallel to the free-text
  // messages above, used to drive the Pipeline Flow stepper during an active run.
  pipeline_stage?: string;
  status?: string;
  duration_ms?: number;
  // Present once on the first "generating" event, once the LLM provider has been resolved.
  model?: string | null;
  provider_available?: boolean;
}

export interface ProviderStatus {
  available: boolean;
  use_self_hosted: boolean;
  base_url: string;
  model: string;
  reachable: boolean;
}

export interface ConfigResponse {
  provider: ProviderStatus;
  retrain_model_enabled: boolean;
  // Present only when RETRAIN_MODEL=true — the second model slot for the (future)
  // retrain-target/Copilot path (any LLM, not tied to a specific one).
  retrain_provider?: ProviderStatus;
  data_dir: string;
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
  // "rule_based" (default) or "retrain-model-v{N}" once a fine-tuned retrain-target model has
  // been promoted and is rephrasing answers — see TSTRCopilotAgent.answer_with_rephrase().
  model_backend: string;
}

export interface RetrainModelEval {
  citation_accuracy: number;
  groundedness: number;
}

export interface RetrainModelHistoryEntry {
  model_version: number;
  trained_at: string;
  cumulative_train_size: number;
  eval: RetrainModelEval;
  status: 'candidate' | 'active' | 'rejected';
}

export interface RetrainModelSnapshot extends RetrainModelHistoryEntry {
  checkpoint_path: string;
  base_model: string;
  history: RetrainModelHistoryEntry[];
}

export interface RetrainModelStatusResponse {
  snapshot: RetrainModelSnapshot | null;
}

export async function fetchTaxonomy(): Promise<TaxonomyResponse> {
  const res = await fetch(`${API_BASE}/api/taxonomy`);
  if (!res.ok) throw new Error('Failed to load taxonomy');
  return res.json();
}

export async function fetchConfig(): Promise<ConfigResponse> {
  const res = await fetch(`${API_BASE}/api/config`);
  if (!res.ok) throw new Error('Failed to load backend config');
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
      industry: config.industry
    })
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Failed to start job');
  }
  return res.json();
}

export async function getJobStatus(jobId: string): Promise<{ status: string; job_id: string }> {
  const res = await fetch(`${API_BASE}/api/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Job not found: ${res.status}`);
  return res.json();
}

/** Shared SSE subscription — used for both the main pipeline job stream and the (separate)
 * retrain-model job stream, which mirrors the same replay-from-start/completion semantics on a
 * different path. */
function subscribeSSE(path: string, onEvent: (ev: JobEvent) => void, onDone: () => void): () => void {
  const es = new EventSource(`${API_BASE}${path}`);

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

export function subscribeJobEvents(jobId: string, onEvent: (ev: JobEvent) => void, onDone: () => void): () => void {
  return subscribeSSE(`/api/jobs/${jobId}/events`, onEvent, onDone);
}

export function subscribeRetrainModelJobEvents(
  jobId: string,
  onEvent: (ev: JobEvent) => void,
  onDone: () => void
): () => void {
  return subscribeSSE(`/api/retrain-model/jobs/${jobId}/events`, onEvent, onDone);
}

export async function startRetrainModelJob(): Promise<{ job_id: string; status: string }> {
  const res = await fetch(`${API_BASE}/api/retrain-model/start`, { method: 'POST' });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || 'Failed to start retrain-model job');
  }
  return res.json();
}

export async function getRetrainModelJobStatus(jobId: string): Promise<{ status: string; job_id: string }> {
  const res = await fetch(`${API_BASE}/api/retrain-model/jobs/${jobId}`);
  if (!res.ok) throw new Error(`Retrain-model job not found: ${res.status}`);
  return res.json();
}

export async function fetchRetrainModelStatus(): Promise<RetrainModelStatusResponse> {
  const res = await fetch(`${API_BASE}/api/retrain-model/status`);
  if (!res.ok) throw new Error('Failed to load retrain-model status');
  return res.json();
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
