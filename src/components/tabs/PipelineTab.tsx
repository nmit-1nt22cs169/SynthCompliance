import { useEffect, useMemo, useRef, useState } from 'react';
import { Badge } from '../Badge';
import { deriveGantt, deriveLiveStages } from '../../lib/derive';
import {
  fetchConfig,
  fetchRetrainModelStatus,
  fetchTaxonomy,
  getJobStatus,
  getRetrainModelJobStatus,
  startJob,
  subscribeJobEvents,
  subscribeRetrainModelJobEvents,
  type ConfigResponse,
  type JobEvent,
  type RetrainModelSnapshot
} from '../../lib/api';
import { formatDuration } from '../../lib/format';
import type { JobConfig, ValidationReport } from '../../types';

// Static explanations for stages that legitimately skip — without these, "skipped" reads as
// "something didn't happen" rather than the (usually good) reason it didn't need to.
function stageSkipCaption(stageName: string, report: ValidationReport | null): string | null {
  if (!report) return null;
  if (stageName === 'Repair Loop') {
    return 'All validators passed on the first pass — no repair needed.';
  }
  if (stageName === 'Model Retraining') {
    if (!report.tstr_metrics?.retrain_enabled) {
      return 'Retraining is disabled (RETRAIN_MODEL not set).';
    }
    if (report.feedback_loop?.improved) {
      const lift = report.tstr_metrics?.recall_lift;
      const liftText = lift != null ? ` (recall lift ${lift >= 0 ? '+' : ''}${(lift * 100).toFixed(1)} pts)` : '';
      return `Recall held steady or improved vs. last run${liftText} — retraining not needed.`;
    }
    return null;
  }
  return null;
}

const INDUSTRIES = [
  { id: 'financial_services', label: 'Financial Services' },
  { id: 'healthcare', label: 'Healthcare' },
  { id: 'retail', label: 'Retail / E-commerce' },
  { id: 'technology', label: 'Technology / SaaS' }
];

const DEFAULT_MIX = { normal: 60, suspicious: 15, violation: 20, false_positive: 5 };

function formatElapsed(ms: number): string {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatClock(ms: number): string {
  return new Date(ms).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

const JOB_STORAGE_KEY = 'synthcompliance:lastJob';
const RETRAIN_MODEL_JOB_STORAGE_KEY = 'synthcompliance:lastRetrainModelJob';

interface StoredJob {
  job_id: string;
  startedAt: number;
}

interface PipelineTabProps {
  report: ValidationReport | null;
  onJobActiveChange?: (active: boolean) => void;
  onJobComplete?: () => void;
}

export function PipelineTab({ report, onJobActiveChange, onJobComplete }: PipelineTabProps) {
  const [packs, setPacks] = useState<string[]>(['SOX', 'GDPR']);
  const [controlClasses, setControlClasses] = useState<string[]>([
    'segregation_of_duties',
    'late_dsar',
    'access_lifecycle_breach'
  ]);
  const [mix, setMix] = useState(DEFAULT_MIX);
  const [nLogs, setNLogs] = useState(500);
  const [industry, setIndustry] = useState('financial_services');
  const [taxonomyClasses, setTaxonomyClasses] = useState<{ id: string; label: string; pack: string }[]>([]);
  const [taxonomyLoading, setTaxonomyLoading] = useState(true);
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startedAt, setStartedAt] = useState<number | null>(null);
  const [finishedAt, setFinishedAt] = useState<number | null>(null);
  const [outcome, setOutcome] = useState<'success' | 'failed' | null>(null);
  const [startRunId, setStartRunId] = useState<string | null>(null);
  const [, forceTick] = useState(0);
  const [activeModel, setActiveModel] = useState<{ model: string | null; available: boolean } | null>(null);
  const [backendConfig, setBackendConfig] = useState<ConfigResponse | null>(null);
  const [configLoading, setConfigLoading] = useState(true);
  const [configError, setConfigError] = useState<string | null>(null);
  const [retrainModelSnapshot, setRetrainModelSnapshot] = useState<RetrainModelSnapshot | null>(null);
  const [retrainModelEvents, setRetrainModelEvents] = useState<JobEvent[]>([]);
  const [retrainModelRunning, setRetrainModelRunning] = useState(false);
  const lastStageRef = useRef<string | null>(null);
  const retrainLastStageRef = useRef<string | null>(null);
  const receivedAnyEventRef = useRef(false);
  const jobLogRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    setTaxonomyLoading(true);
    fetchTaxonomy()
      .then((t) => {
        const classes = Object.entries(t.taxonomy).map(([id, meta]) => ({
          id,
          label: meta.label,
          pack: meta.pack
        }));
        setTaxonomyClasses(classes);
        setTaxonomyError(null);
      })
      .catch((e) => {
        setTaxonomyError(e instanceof Error ? e.message : 'API unavailable — start npm run dev:api');
        setTaxonomyClasses([]);
      })
      .finally(() => setTaxonomyLoading(false));
  }, []);

  const refreshConfig = () => {
    setConfigLoading(true);
    fetchConfig()
      .then((c) => {
        setBackendConfig(c);
        setConfigError(null);
      })
      .catch((e) => {
        setConfigError(e instanceof Error ? e.message : 'Failed to load backend config');
        setBackendConfig(null);
      })
      .finally(() => setConfigLoading(false));
  };

  const refreshRetrainModelStatus = () => {
    fetchRetrainModelStatus()
      .then((r) => setRetrainModelSnapshot(r.snapshot))
      .catch(() => setRetrainModelSnapshot(null));
  };

  // Fetched once for this component's lifetime, not per tab-switch — all tabs stay mounted
  // (see CLAUDE.md), and provider config rarely changes mid-session. `refreshConfig` is exposed
  // via a manual button for the rare case it does (e.g. backend restarted with new env vars).
  useEffect(() => {
    refreshConfig();
    refreshRetrainModelStatus();
  }, []);

  const attachToRetrainModelJob = (jobId: string) => {
    retrainLastStageRef.current = null;
    setRetrainModelRunning(true);
    setRetrainModelEvents([]);
    subscribeRetrainModelJobEvents(
      jobId,
      (ev) => {
        retrainLastStageRef.current = ev.stage;
        setRetrainModelEvents((prev) => [...prev, ev]);
      },
      () => {
        setRetrainModelRunning(false);
        localStorage.removeItem(RETRAIN_MODEL_JOB_STORAGE_KEY);
        refreshRetrainModelStatus();
      }
    );
  };

  // Resume watching an in-progress retrain-model job across a page refresh — same pattern as
  // the main job's resume effect below, on its own storage key since it's a separate job bus.
  useEffect(() => {
    const raw = localStorage.getItem(RETRAIN_MODEL_JOB_STORAGE_KEY);
    if (!raw) return;
    let jobId: string;
    try {
      jobId = (JSON.parse(raw) as { job_id: string }).job_id;
    } catch {
      localStorage.removeItem(RETRAIN_MODEL_JOB_STORAGE_KEY);
      return;
    }
    getRetrainModelJobStatus(jobId)
      .then((job) => {
        if (job.status === 'queued' || job.status === 'running') {
          attachToRetrainModelJob(jobId);
        } else {
          localStorage.removeItem(RETRAIN_MODEL_JOB_STORAGE_KEY);
        }
      })
      .catch(() => localStorage.removeItem(RETRAIN_MODEL_JOB_STORAGE_KEY));
  }, []);

  const isSynced = outcome === 'success' && !!report?.run_id && report.run_id !== startRunId;
  const phase: 'idle' | 'running' | 'finalizing' | 'synced' | 'failed' = running
    ? 'running'
    : outcome === 'failed'
      ? 'failed'
      : outcome === 'success'
        ? (isSynced ? 'synced' : 'finalizing')
        : 'idle';

  useEffect(() => {
    if (phase !== 'running' && phase !== 'finalizing') return;
    const id = setInterval(() => forceTick((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [phase]);

  useEffect(() => {
    const el = jobLogRef.current;
    if (!el) return;
    const nearBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
    if (nearBottom) el.scrollTop = el.scrollHeight;
  }, [jobEvents.length]);

  const mixTotal = mix.normal + mix.suspicious + mix.violation + mix.false_positive;
  const mixValid = mixTotal === 100;

  const filteredClasses = useMemo(
    () => taxonomyClasses.filter((c) => packs.includes(c.pack)),
    [taxonomyClasses, packs]
  );

  const togglePack = (pack: string) => {
    setPacks((prev) => (prev.includes(pack) ? prev.filter((p) => p !== pack) : [...prev, pack]));
  };

  const updateMix = (key: keyof typeof mix, value: number) => {
    setMix((prev) => ({ ...prev, [key]: Math.max(0, Math.min(100, value)) }));
  };

  const attachToJob = (jobId: string) => {
    lastStageRef.current = null;
    receivedAnyEventRef.current = false;
    subscribeJobEvents(
      jobId,
      (ev) => {
        receivedAnyEventRef.current = true;
        lastStageRef.current = ev.stage;
        setJobEvents((prev) => [...prev, ev]);
        if (ev.provider_available !== undefined) {
          setActiveModel({ model: ev.model ?? null, available: ev.provider_available });
        }
      },
      () => {
        setRunning(false);
        onJobActiveChange?.(false);
        // No events ever arrived (e.g. the job_id no longer means anything to this backend
        // process) — nothing meaningful to report, leave phase at idle.
        if (!receivedAnyEventRef.current) return;
        setFinishedAt(Date.now());
        setOutcome(lastStageRef.current === 'failed' ? 'failed' : 'success');
        onJobComplete?.();
        // The main pipeline job may have spawned a separate retrain-model job (RETRAIN_MODEL=true
        // and a regression was detected) — pick it up and start watching it too.
        getJobStatus(jobId)
          .then((job) => {
            const retrainJobId = (job as { result?: { retrain_model_job_id?: string | null } }).result
              ?.retrain_model_job_id;
            if (retrainJobId) {
              localStorage.setItem(RETRAIN_MODEL_JOB_STORAGE_KEY, JSON.stringify({ job_id: retrainJobId }));
              attachToRetrainModelJob(retrainJobId);
            }
          })
          .catch(() => {
            /* nothing to resume */
          });
      }
    );
  };

  const runPipeline = async () => {
    setError(null);
    setRunning(true);
    onJobActiveChange?.(true);
    setJobEvents([]);
    setFinishedAt(null);
    setOutcome(null);
    setActiveModel(null);
    setStartRunId(report?.run_id ?? null);
    const start = Date.now();
    setStartedAt(start);
    const config: JobConfig = {
      packs,
      control_classes: controlClasses,
      scenario_mix: {
        normal: mix.normal / 100,
        suspicious: mix.suspicious / 100,
        violation: mix.violation / 100,
        false_positive: mix.false_positive / 100
      },
      n_logs: nLogs,
      industry
    };
    try {
      const { job_id } = await startJob(config);
      localStorage.setItem(JOB_STORAGE_KEY, JSON.stringify({ job_id, startedAt: start } as StoredJob));
      attachToJob(job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
      onJobActiveChange?.(false);
      setFinishedAt(Date.now());
      setOutcome('failed');
    }
  };

  // Resume watching (or restore the history of) the last job across a page refresh — the
  // backend SSE stream replays its full event buffer from the start on every new connection,
  // so re-subscribing naturally rehydrates the whole log, live-continuing if still running.
  useEffect(() => {
    const raw = localStorage.getItem(JOB_STORAGE_KEY);
    if (!raw) return;
    let stored: StoredJob;
    try {
      stored = JSON.parse(raw) as StoredJob;
    } catch {
      localStorage.removeItem(JOB_STORAGE_KEY);
      return;
    }
    getJobStatus(stored.job_id)
      .then((job) => {
        setStartedAt(stored.startedAt);
        setStartRunId(null);
        const active = job.status === 'queued' || job.status === 'running';
        setRunning(active);
        if (active) onJobActiveChange?.(true);
        attachToJob(stored.job_id);
      })
      .catch(() => {
        // Backend no longer knows this job (likely restarted since) — nothing to resume.
        localStorage.removeItem(JOB_STORAGE_KEY);
      });
  }, []);

  const gantt = report ? deriveGantt(report) : null;
  const latest = jobEvents[jobEvents.length - 1];
  const showLiveStages = phase === 'running' || phase === 'finalizing';
  const liveStages = useMemo(() => deriveLiveStages(jobEvents), [jobEvents]);
  const displayStages = showLiveStages ? liveStages : report?.pipeline_stages ?? null;

  return (
    <div>
      <div className="glass-panel tab-panel panel-pad">
        <div className="job-feed-header">
          <div className="panel-title" style={{ marginBottom: 0 }}>
            Backend Configuration
          </div>
          <button type="button" className="chip" onClick={refreshConfig} disabled={configLoading}>
            {configLoading ? 'Checking…' : 'Refresh'}
          </button>
        </div>
        {configError && <div className="wizard-error">{configError}</div>}
        {backendConfig && (
          <>
            <div className="config-section-label" style={{ marginTop: 12 }}>
              Generation model — writes audit-log content during a run
            </div>
            <div className="proof-metrics">
              <div className="proof-metric">
                <span className="proof-metric-label">Mode</span>
                <span className="proof-metric-value">
                  {backendConfig.provider.available
                    ? backendConfig.provider.use_self_hosted
                      ? 'Self-hosted / Ollama'
                      : 'Hosted'
                    : 'None (deterministic)'}
                </span>
              </div>
              <div className="proof-metric">
                <span className="proof-metric-label">Model name</span>
                <span className="proof-metric-value">{backendConfig.provider.available ? backendConfig.provider.model : '—'}</span>
              </div>
              <div className="proof-metric">
                <span className="proof-metric-label">Endpoint reachable</span>
                <Badge status={backendConfig.provider.available ? (backendConfig.provider.reachable ? 'pass' : 'fail') : 'skipped'} />
              </div>
              <div className="proof-metric">
                <span className="proof-metric-label">Retraining</span>
                <span className="proof-metric-value">{backendConfig.retrain_model_enabled ? 'On' : 'Off'}</span>
              </div>
            </div>
            {backendConfig.retrain_provider && (
              <>
                <div className="config-section-label" style={{ marginTop: 16 }}>
                  Retrain-target model — the (future) model retrained for Copilot, independent of the one above
                </div>
                <div className="proof-metrics">
                  <div className="proof-metric">
                    <span className="proof-metric-label">Mode</span>
                    <span className="proof-metric-value">
                      {backendConfig.retrain_provider.available
                        ? backendConfig.retrain_provider.use_self_hosted
                          ? 'Self-hosted / Ollama'
                          : 'Hosted'
                        : 'Not configured'}
                    </span>
                  </div>
                  <div className="proof-metric">
                    <span className="proof-metric-label">Model name</span>
                    <span className="proof-metric-value">
                      {backendConfig.retrain_provider.available ? backendConfig.retrain_provider.model : '—'}
                    </span>
                  </div>
                  <div className="proof-metric">
                    <span className="proof-metric-label">Endpoint reachable</span>
                    <Badge
                      status={
                        backendConfig.retrain_provider.available ? (backendConfig.retrain_provider.reachable ? 'pass' : 'fail') : 'skipped'
                      }
                    />
                  </div>
                </div>
              </>
            )}
            {retrainModelSnapshot && (
              <>
                <div className="config-section-label" style={{ marginTop: 16 }}>
                  Retrain-target model — last fine-tune result
                </div>
                <div className="proof-metrics">
                  <div className="proof-metric">
                    <span className="proof-metric-label">Version</span>
                    <span className="proof-metric-value">v{retrainModelSnapshot.model_version}</span>
                  </div>
                  <div className="proof-metric">
                    <span className="proof-metric-label">Status</span>
                    <Badge status={retrainModelSnapshot.status === 'active' ? 'pass' : retrainModelSnapshot.status === 'rejected' ? 'fail' : 'skipped'} />
                  </div>
                  <div className="proof-metric">
                    <span className="proof-metric-label">Citation accuracy</span>
                    <span className="proof-metric-value">{(retrainModelSnapshot.eval.citation_accuracy * 100).toFixed(0)}%</span>
                  </div>
                  <div className="proof-metric">
                    <span className="proof-metric-label">Groundedness</span>
                    <span className="proof-metric-value">{(retrainModelSnapshot.eval.groundedness * 100).toFixed(0)}%</span>
                  </div>
                </div>
              </>
            )}
          </>
        )}
      </div>

      {(retrainModelRunning || retrainModelEvents.length > 0) && (
        <div className="glass-panel tab-panel panel-pad">
          <div className="job-feed-header">
            <div className="panel-title" style={{ marginBottom: 0 }}>
              Retrain-Target Model — Training
            </div>
            {retrainModelRunning && (
              <span className="job-timer-status job-timer-status-running">Running…</span>
            )}
          </div>
          <div className="job-log">
            {retrainModelEvents.map((ev, i) => (
              <div key={i} className="job-log-line">
                <span className="job-stage">[{ev.stage}]</span> {ev.message}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="glass-panel tab-panel wizard-panel">
        <div className="panel-title">Pipeline Wizard</div>
        <div className="wizard-grid">
          <div className="wizard-field">
            <label className="wizard-label">Regulation Packs</label>
            <div className="chip-row">
              {['SOX', 'GDPR'].map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip${packs.includes(p) ? ' active' : ''}`}
                  onClick={() => togglePack(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="control-classes">
              Control Classes
            </label>
            <select
              id="control-classes"
              multiple
              className="wizard-select"
              size={6}
              value={controlClasses}
              disabled={taxonomyLoading || !!taxonomyError}
              onChange={(e) => {
                const selected = Array.from(e.target.selectedOptions, (o) => o.value);
                setControlClasses(selected);
              }}
            >
              {taxonomyLoading && <option disabled>Loading taxonomy from API…</option>}
              {taxonomyError && <option disabled>{taxonomyError}</option>}
              {!taxonomyLoading &&
                !taxonomyError &&
                filteredClasses.map((c) => (
                  <option key={c.id} value={c.id}>
                    [{c.pack}] {c.label}
                  </option>
                ))}
            </select>
            <div className="wizard-hint">Hold Ctrl/Cmd to select multiple. Default demo: SoD + Late DSAR + Access Lifecycle.</div>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="industry">
              Industry Profile
            </label>
            <select
              id="industry"
              className="wizard-select single"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
            >
              {INDUSTRIES.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.label}
                </option>
              ))}
            </select>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="n-logs">
              Dataset Size (audit logs)
            </label>
            <input
              id="n-logs"
              type="number"
              min={50}
              max={2000}
              step={50}
              className="wizard-input"
              value={nLogs}
              onChange={(e) => setNLogs(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="wizard-field" style={{ marginTop: 16 }}>
          <label className="wizard-label">Scenario Mix (must sum to 100%)</label>
          <div className="slider-grid">
            {(['normal', 'suspicious', 'violation', 'false_positive'] as const).map((key) => (
              <div key={key} className="slider-row">
                <span className="slider-name">{key.replace('_', ' ')}</span>
                <input
                  type="range"
                  className="slider-input"
                  min={0}
                  max={100}
                  value={mix[key]}
                  onChange={(e) => updateMix(key, Number(e.target.value))}
                />
                <span className="slider-val">{mix[key]}%</span>
              </div>
            ))}
          </div>
          <div className={`mix-total${mixValid ? '' : ' invalid'}`}>Total: {mixTotal}%</div>
        </div>

        <div className="wizard-actions">
          <button
            type="button"
            className="copilot-button"
            disabled={running || !mixValid || packs.length === 0 || configLoading || !backendConfig}
            onClick={() => runPipeline()}
          >
            {running ? 'Running…' : 'Run Pipeline'}
          </button>
          {!running && (configLoading || !backendConfig) && (
            <span className="wizard-hint" style={{ alignSelf: 'center' }}>
              {configLoading
                ? 'Loading backend configuration…'
                : 'Backend configuration not loaded — check that npm run dev:api is running, then click Refresh above.'}
            </span>
          )}
        </div>

        {error && <div className="wizard-error">{error}</div>}

        {(running || jobEvents.length > 0) && (
          <div className="job-feed">
            <div className="job-feed-header">
              <div className="panel-title" style={{ marginBottom: 0 }}>
                Live Job Stream
              </div>
              {phase !== 'idle' && startedAt && (
                <div className="job-timer">
                  <span className={`job-timer-status job-timer-status-${phase}`}>
                    {phase === 'running' && `Running · ${formatElapsed(Date.now() - startedAt)}`}
                    {phase === 'finalizing' && `Finalizing… writing output · ${formatElapsed((finishedAt ?? Date.now()) - startedAt)}`}
                    {phase === 'synced' && `Completed in ${formatElapsed((finishedAt ?? Date.now()) - startedAt)}`}
                    {phase === 'failed' && `Failed after ${formatElapsed((finishedAt ?? Date.now()) - startedAt)}`}
                  </span>
                  <span className="job-timer-detail">
                    Started {formatClock(startedAt)}
                    {finishedAt ? ` · Ended ${formatClock(finishedAt)}` : ''}
                  </span>
                </div>
              )}
              {activeModel && (
                <div className="job-timer">
                  <span className="job-timer-status">
                    {activeModel.available ? `Model: ${activeModel.model}` : 'No provider — deterministic generation'}
                  </span>
                </div>
              )}
            </div>
            {latest && (
              <div className="job-latest">
                <Badge status={latest.stage === 'failed' ? 'fail' : latest.stage === 'complete' ? 'pass' : 'warn'} />
                <span>{latest.message}</span>
                {latest.count != null && latest.total != null && (
                  <span className="job-count">
                    {latest.count} / {latest.total}
                  </span>
                )}
              </div>
            )}
            <div className="job-log" ref={jobLogRef}>
              {jobEvents.map((ev, i) => (
                <div key={i} className="job-log-line">
                  <span className="job-stage">[{ev.stage}]</span> {ev.message}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {gantt && report && (
        <div className="glass-panel tab-panel panel-pad">
          <div className="panel-title">Stage Durations</div>
          <div className="gantt">
            {gantt.map((g) => (
              <div className="gantt-row" key={g.stage}>
                <span className="gantt-label">{g.stage}</span>
                <div className="gantt-track">
                  <div
                    className={`gantt-bar${g.status === 'running' ? ' gantt-bar-running' : ''}`}
                    style={{ width: `${g.pct}%` }}
                  />
                </div>
                <span className="gantt-value">{formatDuration(g.durationMs)}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {displayStages && (
        <div className="glass-panel panel-pad tab-panel">
          <div className="panel-title" style={{ marginBottom: 16 }}>
            Pipeline Flow
            {showLiveStages && (
              <span className="job-timer-status job-timer-status-running" style={{ marginLeft: 10, fontSize: 'var(--text-2xs)' }}>
                live
              </span>
            )}
          </div>
          {displayStages.map((s) => {
            const caption = !showLiveStages ? stageSkipCaption(s.stage, report) : null;
            return (
              <div key={s.stage}>
                <div className={`pipeline-row${s.status === 'running' ? ' pipeline-row-running' : ''}`}>
                  <span className="pipeline-stage-name">{s.stage}</span>
                  <div className="pipeline-row-right">
                    <span className="pipeline-duration">{formatDuration(s.duration_ms)}</span>
                    <Badge status={s.status} />
                  </div>
                </div>
                {s.status === 'skipped' && caption && <div className="repair-note">{caption}</div>}
              </div>
            );
          })}
          {!showLiveStages && report?.repair_log && report.repair_log.repaired_log_ids.length > 0 && (
            <div className="repair-note">
              Repair loop fixed {report.repair_log.repaired_log_ids.length} row(s) in {report.repair_log.iterations} iteration(s).
            </div>
          )}
        </div>
      )}
    </div>
  );
}
