import { useState } from 'react';
import { SeverityBadge } from '../Badge';
import type { Violation } from '../../types';

interface CopilotTabProps {
  violations: Violation[];
}

const KEYWORD_MAP: { kw: string; type: string }[] = [
  { kw: 'segregation of duties', type: 'segregation_of_duties' },
  { kw: 'segregation', type: 'segregation_of_duties' },
  { kw: 'unauthorized access', type: 'unauthorized_access' },
  { kw: 'unauthorized', type: 'unauthorized_access' },
  { kw: 'late dsar', type: 'late_dsar' },
  { kw: 'dsar', type: 'late_dsar' },
  { kw: 'missing approval', type: 'missing_approval' },
  { kw: 'approval', type: 'missing_approval' }
];

function runQuery(violations: Violation[], rawQuery: string): Violation[] {
  const q = rawQuery.toLowerCase().trim();
  if (!q) return [];
  const matchedTypes = new Set<string>();
  KEYWORD_MAP.forEach(({ kw, type }) => {
    if (q.includes(kw)) matchedTypes.add(type);
  });
  let matches: Violation[];
  if (matchedTypes.size > 0) {
    matches = violations.filter((v) => matchedTypes.has(v.violation_type));
  } else {
    matches = violations.filter(
      (v) =>
        v.violation_type.replace(/_/g, ' ').includes(q) ||
        v.explanation.toLowerCase().includes(q) ||
        v.control_id.toLowerCase().includes(q)
    );
  }
  return matches.slice(0, 5);
}

export function CopilotTab({ violations }: CopilotTabProps) {
  const [queryText, setQueryText] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [results, setResults] = useState<Violation[]>([]);

  const submit = () => {
    if (!queryText.trim()) {
      setHasSearched(false);
      setResults([]);
      return;
    }
    setResults(runQuery(violations, queryText));
    setHasSearched(true);
  };

  return (
    <div className="glass-panel copilot-panel">
      <div className="panel-title">Compliance Copilot</div>
      <div className="copilot-query-row">
        <input
          type="text"
          className="copilot-input"
          placeholder="Ask about a violation, e.g. 'unauthorized access' or 'late DSAR'"
          value={queryText}
          onChange={(e) => setQueryText(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') submit();
          }}
        />
        <button className="copilot-button" onClick={submit}>
          Query
        </button>
      </div>

      {hasSearched && (
        <div className="copilot-results">
          {results.length > 0 ? (
            results.map((r) => (
              <div className="copilot-result-card" key={r.violation_id}>
                <div className="copilot-result-head">
                  <span className="copilot-control-id">{r.control_id}</span>
                  <SeverityBadge severity={r.severity} />
                  <span className="copilot-evidence">evidence: {r.log_id}</span>
                </div>
                <div className="copilot-explanation">{r.explanation}</div>
              </div>
            ))
          ) : (
            <div className="copilot-empty">
              No matching violations found for that query. Try "segregation of duties", "unauthorized access",
              "late DSAR", or "missing approval".
            </div>
          )}
        </div>
      )}
    </div>
  );
}
