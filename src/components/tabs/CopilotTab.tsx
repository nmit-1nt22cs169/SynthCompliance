import { useEffect, useState } from 'react';
import { Badge, SeverityBadge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import { fetchRetrainModelStatus, queryCopilot, type RetrainModelSnapshot } from '../../lib/api';
import type { AuditLog, DataTable, Violation } from '../../types';

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

  // Static, fetched once — same "rare to change mid-session" reasoning as ProofTab/PipelineTab's
  // config fetches. Tells the user upfront whether the rephrasing layer below is actually live
  // before they've run a single query.
  useEffect(() => {
    fetchRetrainModelStatus()
      .then((r) => setRetrainSnapshot(r.snapshot))
      .catch(() => setRetrainSnapshot(null));
  }, []);

  const rephraseLive = retrainSnapshot?.status === 'active';

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
        <Badge status={rephraseLive ? 'pass' : 'skipped'} />
        <span className="copilot-status-text">
          {rephraseLive
            ? `AI rephrasing is on — a trained model (v${retrainSnapshot?.model_version}) rewrites these answers in more natural language. The facts underneath never change.`
            : "AI rephrasing is off for this run — answers are shown exactly as matched, in plain rule-based form. This optional layer isn't turned on yet."}
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
