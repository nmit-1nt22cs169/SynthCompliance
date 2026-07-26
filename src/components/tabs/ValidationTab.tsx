import { Fragment, useMemo, useState } from 'react';
import { Badge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import { deriveFlaggedRows, deriveValidators, deriveViolationMatrix } from '../../lib/derive';
import type { DataTable, ValidationReport, Violation } from '../../types';

interface ValidationTabProps {
  report: ValidationReport;
  violations: Violation[];
  jobActive?: boolean;
  onJump?: (table: DataTable, id: string) => void;
}

const VIOLATION_ID_RE = /^V-\d+$/;

function heatColor(count: number, max: number): string {
  if (count === 0 || max === 0) return 'transparent';
  const t = count / max;
  return `rgba(224, 85, 90, ${0.12 + t * 0.55})`;
}

export function ValidationTab({ report, violations, jobActive, onJump }: ValidationTabProps) {
  const validators = deriveValidators(report);
  const flaggedRows = deriveFlaggedRows(report);
  const matrix = useMemo(() => deriveViolationMatrix(violations), [violations]);
  const [query, setQuery] = useState('');

  const filteredRows = query
    ? flaggedRows.filter((f) =>
        [f.validator, f.id, f.reason].some((v) => v.toLowerCase().includes(query.toLowerCase()))
      )
    : flaggedRows;

  const handleRowClick = (id: string) => {
    if (!onJump) return;
    onJump(VIOLATION_ID_RE.test(id) ? 'violations' : 'auditLogs', id);
  };

  return (
    <div>
      {jobActive && <StaleBanner />}
      <div className="validator-grid">
        {validators.map((v) => (
          <div className="glass-panel validator-card" key={v.key}>
            <div className="validator-card-header">
              <span className="validator-name">{v.name}</span>
              <Badge status={v.status} />
            </div>
            <span className="validator-detail">{v.detail}</span>
          </div>
        ))}
      </div>

      {matrix.types.length > 0 && (
        <div className="glass-panel tab-panel panel-pad">
          <div className="panel-title">Violation Breakdown — Type × Severity</div>
          <div className="matrix-wrap">
            <table className="data-table matrix-table">
              <thead>
                <tr>
                  <th>Violation Type</th>
                  {matrix.severities.map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {matrix.types.map((type) => (
                  <tr key={type}>
                    <td>{type.replace(/_/g, ' ')}</td>
                    {matrix.severities.map((sev) => {
                      const cell = matrix.cells.find((c) => c.type === type && c.severity === sev);
                      const count = cell?.count ?? 0;
                      return (
                        <td key={sev} className="matrix-cell" style={{ background: heatColor(count, matrix.max) }}>
                          {count || ''}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="glass-panel panel-pad">
        <div className="table-toolbar" style={{ marginBottom: 0 }}>
          <div className="panel-title" style={{ marginBottom: 0 }}>
            Flagged Rows
          </div>
          <input
            type="text"
            className="wizard-input table-search"
            placeholder="Filter by validator, ID, or reason…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <span className="table-count">
            {filteredRows.length} / {flaggedRows.length}
          </span>
        </div>
        <div className="flagged-table" style={{ marginTop: 12 }}>
          <div className="flagged-header">Validator</div>
          <div className="flagged-header">Row / Violation ID</div>
          <div className="flagged-header">Reason</div>
          {filteredRows.map((f, i) => (
            <Fragment key={i}>
              <div className="flagged-cell validator">{f.validator}</div>
              <div className="flagged-cell id">
                {onJump ? (
                  <button type="button" className="link-btn" onClick={() => handleRowClick(f.id)}>
                    {f.id}
                  </button>
                ) : (
                  f.id
                )}
              </div>
              <div className="flagged-cell reason">{f.reason}</div>
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
