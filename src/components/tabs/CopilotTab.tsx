import { useEffect, useState } from 'react';
import { Badge, SeverityBadge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import {
  fetchConfig,
  fetchRetrainModelStatus,
  getRetrainModelJobStatus,
  queryCopilot,
  type RetrainModelSnapshot
} from '../../lib/api';
import type { AuditLog, DataTable, Violation } from '../../types';

// Same key PipelineTab.tsx writes when it kicks off a retrain-model job, so this tab can tell
// "currently training" apart from "enabled but nothing has triggered a retrain yet" without
// needing that state lifted up through props.
const RETRAIN_MODEL_JOB_STORAGE_KEY = 'synthcompliance:lastRetrainModelJob';

interface CopilotTabProps {
  violations: Violation[];
  auditLogs: AuditLog[];
  jobActive?: boolean;
  onJump?: (table: DataTable, id: string) => void;
}

export function CopilotTab({ violations: _violations, jobActive, onJump }: CopilotTabProps) {
  const [queryText, setQueryText] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [answer, setAnswer] = useState<string | null>(null);
  const [modelBackend, setModelBackend] = useState<string | null>(null);
  const [results, setResults] = useState<
    {
      violation_id: string;
      log_id: string;
      control_id: string;
      severity: Violation['severity'];
      explanation: string;
    }[]
  >([]);
  const [evidenceIds, setEvidenceIds] = useState<string[]>([]);
  const [retrainSnapshot, setRetrainSnapshot] = useState<RetrainModelSnapshot | null>(null);
  const [retrainModelEnabled, setRetrainModelEnabled] = useState<boolean | null>(null);
  const [retrainTraining, setRetrainTraining] = useState(false);

  // Static, fetched once — same "rare to change mid-session" reasoning as ProofTab/PipelineTab's
  // config fetches. Tells the user upfront whether the rephrasing layer below is actually live
  // before they've run a single query.
  useEffect(() => {
    fetchConfig()
      .then((c) => setRetrainModelEnabled(c.retrain_model_enabled))
      .catch(() => setRetrainModelEnabled(null));
    fetchRetrainModelStatus()
      .then((r) => setRetrainSnapshot(r.snapshot))
      .catch(() => setRetrainSnapshot(null));
    // Best-effort: a retrain-model job PipelineTab started may still be running in the
    // background (a real LoRA pass can run far longer than the pipeline job itself), in which
    // case there's deliberately no promoted snapshot yet — that's "training," not "off."
    const raw = localStorage.getItem(RETRAIN_MODEL_JOB_STORAGE_KEY);
    if (raw) {
      try {
        const { job_id } = JSON.parse(raw) as { job_id: string };
        getRetrainModelJobStatus(job_id)
          .then((s) => setRetrainTraining(s.status === 'queued' || s.status === 'running'))
          .catch(() => setRetrainTraining(false));
      } catch {
        setRetrainTraining(false);
      }
    }
  }, []);

  // Four distinct real states, not a pass/skip binary — collapsing "rejected" or "training" into
  // the same "off" copy as "never enabled" is misleading: RETRAIN_MODEL can be true, a retrain can
  // have actually run for this data, and the badge still needs to say so accurately.
  const rephraseState: 'off' | 'training' | 'active' | 'rejected' | 'pending' =
    retrainModelEnabled === false
      ? 'off'
      : retrainTraining
        ? 'training'
        : retrainSnapshot?.status === 'active'
          ? 'active'
          : retrainSnapshot?.status === 'rejected'
            ? 'rejected'
            : 'pending';

  const submit = async () => {
    if (!queryText.trim()) {
      setHasSearched(false);
      setResults([]);
      setAnswer(null);
      setError(null);
      return;
    }
    setLoading(true);
    setHasSearched(true);
    setError(null);
    try {
      const resp = await queryCopilot(queryText);
      setAnswer(resp.answer);
      setModelBackend(resp.model_backend ?? 'rule_based');
      setEvidenceIds(resp.evidence_log_ids);
      setResults(
        resp.citations.map((c) => ({
          violation_id: c.violation_id,
          log_id: c.log_id,
          control_id: c.control_id,
          severity: c.severity as Violation['severity'],
          explanation: c.explanation
        }))
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Copilot API unavailable — ensure dev:api is running');
      setResults([]);
      setAnswer(null);
      setModelBackend(null);
      setEvidenceIds([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel copilot-panel">
      {jobActive && <StaleBanner />}
      <div className="panel-title">Compliance Copilot</div>
      <p className="copilot-sub">
        Every answer below is matched directly from this run's real data — the facts and evidence
        you see are never invented, no matter what's toggled below.
      </p>
      <div className="copilot-status-row">
        <Badge
          status={
            rephraseState === 'active'
              ? 'pass'
              : rephraseState === 'rejected'
                ? 'fail'
                : rephraseState === 'training'
                  ? 'warn'
                  : 'skipped'
          }
        />
        <span className="copilot-status-text">
          {rephraseState === 'active' &&
            `AI rephrasing is on — a trained model (v${retrainSnapshot?.model_version}) rewrites these answers in more natural language. The facts underneath never change.`}
          {rephraseState === 'rejected' &&
            `AI rephrasing retrained after a recent recall regression (v${retrainSnapshot?.model_version}), but the new checkpoint didn't beat the previously active one on citation accuracy/groundedness — it was rejected, so answers are still shown in plain rule-based form.`}
          {rephraseState === 'training' &&
            'AI rephrasing retrain is currently running in the background (triggered by the last run\'s recall regression) — answers are shown in plain rule-based form until it finishes and is evaluated.'}
          {rephraseState === 'pending' &&
            "AI rephrasing is enabled but hasn't been triggered yet — it only fires after a run's recall fails to improve on the previous one. Answers are shown in plain rule-based form until then."}
          {rephraseState === 'off' &&
            "AI rephrasing is off for this deployment (RETRAIN_MODEL is not enabled) — answers are shown exactly as matched, in plain rule-based form."}
        </span>
      </div>
      <div className="copilot-query-row">
        <input
          type="text"
          className="copilot-input"
          placeholder="e.g. Which logs show an SoD violation involving invoice approval?"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
          }}
        />
        <button className="copilot-button" onClick={submit} disabled={loading}>
          {loading ? 'Querying…' : 'Query'}
        </button>
      </div>

      {error && <div className="wizard-error">{error}</div>}

      {hasSearched && !error && (
        <div className="copilot-results">
          {answer && modelBackend && (
            <div className="copilot-model-backend">
              {modelBackend === 'rule_based' ? 'Answered by: rule-based' : `Rephrased by: ${modelBackend}`}
            </div>
          )}
          {answer && <div className="copilot-answer">{answer}</div>}
          {results.length > 0 ? (
            results.map((r) => (
              <div className="copilot-result-card" key={r.violation_id}>
                <div className="copilot-result-head">
                  <span className="copilot-control-id">{r.control_id}</span>
                  <SeverityBadge severity={r.severity} />
                  <span className="copilot-evidence">
                    evidence:{' '}
                    {onJump ? (
                      <button type="button" className="link-btn" onClick={() => onJump('auditLogs', r.log_id)}>
                        {r.log_id}
                      </button>
                    ) : (
                      r.log_id
                    )}
                  </span>
                </div>
                <div className="copilot-explanation">{r.explanation}</div>
              </div>
            ))
          ) : (
            <div className="copilot-empty">No matching violations in the live corpus for that query.</div>
          )}
          {evidenceIds.length > 0 && (
            <div className="copilot-evidence-list">
              evidence_log_ids:{' '}
              {evidenceIds.map((id, i) => (
                <span key={id}>
                  {i > 0 && ', '}
                  {onJump ? (
                    <button type="button" className="link-btn" onClick={() => onJump('auditLogs', id)}>
                      {id}
                    </button>
                  ) : (
                    id
                  )}
                </span>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
