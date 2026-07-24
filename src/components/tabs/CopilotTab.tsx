import { useState } from 'react';
import { SeverityBadge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import { queryCopilot } from '../../lib/api';
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
      setEvidenceIds([]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="glass-panel copilot-panel">
      {jobActive && <StaleBanner />}
      <div className="panel-title">Compliance Copilot</div>
      <p className="copilot-sub">Live API — rule-grounded retrieval with cited evidence_log_ids from the current run.</p>
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
