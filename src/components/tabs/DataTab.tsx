import { useEffect, useState } from 'react';
import { exportBundleUrl } from '../../lib/api';
import { deriveActivityBars } from '../../lib/derive';
import { StaleBanner } from '../StaleBanner';
import type { AuditLog, DataTable, QaPair, Violation } from '../../types';
import type { JumpTarget } from '../../App';

interface DataTabProps {
  auditLogs: AuditLog[];
  violations: Violation[];
  qaPairs: QaPair[];
  jobActive?: boolean;
  jumpTarget?: JumpTarget | null;
  onJumpConsumed?: () => void;
}

function useTableControls<T>(rows: T[], idKey: keyof T, highlightId: string | null) {
  const [query, setQuery] = useState('');
  const [sortKey, setSortKey] = useState<keyof T | null>(null);
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');
  const [visibleCount, setVisibleCount] = useState(25);

  useEffect(() => {
    if (highlightId) {
      setQuery(highlightId);
      setVisibleCount(25);
    }
  }, [highlightId]);

  const filtered = query
    ? rows.filter((r) =>
        Object.values(r as Record<string, unknown>).some((v) => String(v).toLowerCase().includes(query.toLowerCase()))
      )
    : rows;

  const sorted = sortKey
    ? [...filtered].sort((a, b) => {
        const av = a[sortKey];
        const bv = b[sortKey];
        const cmp =
          typeof av === 'number' && typeof bv === 'number' ? av - bv : String(av).localeCompare(String(bv));
        return sortDir === 'asc' ? cmp : -cmp;
      })
    : filtered;

  const visible = sorted.slice(0, visibleCount);

  const toggleSort = (key: keyof T) => {
    if (sortKey === key) {
      setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  return {
    query,
    setQuery,
    sortKey,
    sortDir,
    toggleSort,
    visible,
    totalFiltered: sorted.length,
    totalAll: rows.length,
    showMore: () => setVisibleCount((n) => n + 25),
    isHighlighted: (row: T) => highlightId != null && String(row[idKey]) === highlightId
  };
}

function SortHeader<T>({
  label,
  column,
  active,
  dir,
  onSort
}: {
  label: string;
  column: keyof T;
  active: boolean;
  dir: 'asc' | 'desc';
  onSort: (col: keyof T) => void;
}) {
  return (
    <th onClick={() => onSort(column)} className={active ? 'sorted' : ''}>
      {label}
      {active && <span className="sort-arrow">{dir === 'asc' ? ' ▲' : ' ▼'}</span>}
    </th>
  );
}

export function DataTab({ auditLogs, violations, qaPairs, jobActive, jumpTarget, onJumpConsumed }: DataTabProps) {
  const hasLiveData = auditLogs.length > 0 || violations.length > 0 || qaPairs.length > 0;

  const highlightFor = (table: DataTable): string | null =>
    jumpTarget && jumpTarget.table === table ? jumpTarget.id : null;

  const logCtl = useTableControls(auditLogs, 'log_id', highlightFor('auditLogs'));
  const violationCtl = useTableControls(violations, 'violation_id', highlightFor('violations'));
  const qaCtl = useTableControls(qaPairs, 'qa_id', highlightFor('qaPairs'));

  useEffect(() => {
    if (jumpTarget) {
      const t = setTimeout(() => onJumpConsumed?.(), 50);
      return () => clearTimeout(t);
    }
  }, [jumpTarget, onJumpConsumed]);

  const systemBars = deriveActivityBars(auditLogs, 'system');
  const roleBars = deriveActivityBars(auditLogs, 'role');

  return (
    <div>
      {jobActive && <StaleBanner />}
      <div className="data-toolbar glass-panel">
        <div>
          <div className="panel-title" style={{ marginBottom: 4 }}>
            Dataset Browser
          </div>
          <div className="data-counts">
            {auditLogs.length} audit logs · {violations.length} violations · {qaPairs.length} Q&amp;A pairs
          </div>
        </div>
        <a className="copilot-button data-export" href={exportBundleUrl()} download="synthcompliance_export.zip">
          Download Export Bundle
        </a>
      </div>

      {!hasLiveData && (
        <div className="glass-panel" style={{ padding: 24 }}>
          <div className="panel-title" style={{ marginBottom: 8 }}>
            Waiting for live run output
          </div>
          <div className="validation-detail">
            The next pipeline run will write the newest audit logs, violations, and QA pairs into the live dataset bundle.
          </div>
        </div>
      )}

      {hasLiveData && (
        <>
          <div className="overview-row-2">
            <div className="glass-panel panel-pad">
              <div className="panel-title">Activity by System</div>
              {systemBars.map((b) => (
                <div className="activity-bar-row" key={b.label}>
                  <span className="activity-bar-label">{b.label}</span>
                  <div className="activity-bar-track">
                    <div className="activity-bar-fill" style={{ width: `${b.pct}%` }} />
                  </div>
                  <span className="activity-bar-count">{b.count}</span>
                </div>
              ))}
            </div>
            <div className="glass-panel panel-pad">
              <div className="panel-title">Activity by Role</div>
              {roleBars.map((b) => (
                <div className="activity-bar-row" key={b.label}>
                  <span className="activity-bar-label">{b.label}</span>
                  <div className="activity-bar-track">
                    <div className="activity-bar-fill" style={{ width: `${b.pct}%`, background: 'var(--accent)' }} />
                  </div>
                  <span className="activity-bar-count">{b.count}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="glass-panel tab-panel panel-pad">
            <div className="panel-title">Audit Logs</div>
            <div className="table-toolbar">
              <input
                type="text"
                className="wizard-input table-search"
                placeholder="Search audit logs…"
                value={logCtl.query}
                onChange={(e) => logCtl.setQuery(e.target.value)}
              />
              <span className="table-count">
                {logCtl.totalFiltered} / {logCtl.totalAll}
              </span>
            </div>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <SortHeader label="Log ID" column="log_id" active={logCtl.sortKey === 'log_id'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Timestamp" column="timestamp" active={logCtl.sortKey === 'timestamp'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="User" column="user_id" active={logCtl.sortKey === 'user_id'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Action" column="action" active={logCtl.sortKey === 'action'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Resource" column="resource" active={logCtl.sortKey === 'resource'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Outcome" column="outcome" active={logCtl.sortKey === 'outcome'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Role" column="role" active={logCtl.sortKey === 'role'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="Sensitivity" column="sensitivity" active={logCtl.sortKey === 'sensitivity'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                    <SortHeader label="System" column="system" active={logCtl.sortKey === 'system'} dir={logCtl.sortDir} onSort={logCtl.toggleSort} />
                  </tr>
                </thead>
                <tbody>
                  {logCtl.visible.map((r) => (
                    <tr key={r.log_id} className={logCtl.isHighlighted(r) ? 'highlighted' : ''}>
                      <td className="mono">{r.log_id}</td>
                      <td className="mono">{r.timestamp}</td>
                      <td className="mono">{r.user_id}</td>
                      <td>{r.action}</td>
                      <td className="mono">{r.resource}</td>
                      <td>{r.outcome}</td>
                      <td>{r.role}</td>
                      <td>{r.sensitivity}</td>
                      <td>{r.system}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {logCtl.visible.length < logCtl.totalFiltered && (
              <button type="button" className="link-btn table-more" onClick={logCtl.showMore}>
                Show more ({logCtl.totalFiltered - logCtl.visible.length} remaining)
              </button>
            )}
          </div>

          <div className="glass-panel tab-panel panel-pad">
            <div className="panel-title">Violations</div>
            <div className="table-toolbar">
              <input
                type="text"
                className="wizard-input table-search"
                placeholder="Search violations…"
                value={violationCtl.query}
                onChange={(e) => violationCtl.setQuery(e.target.value)}
              />
              <span className="table-count">
                {violationCtl.totalFiltered} / {violationCtl.totalAll}
              </span>
            </div>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <SortHeader label="Violation ID" column="violation_id" active={violationCtl.sortKey === 'violation_id'} dir={violationCtl.sortDir} onSort={violationCtl.toggleSort} />
                    <SortHeader label="Log ID" column="log_id" active={violationCtl.sortKey === 'log_id'} dir={violationCtl.sortDir} onSort={violationCtl.toggleSort} />
                    <SortHeader label="Type" column="violation_type" active={violationCtl.sortKey === 'violation_type'} dir={violationCtl.sortDir} onSort={violationCtl.toggleSort} />
                    <SortHeader label="Control" column="control_id" active={violationCtl.sortKey === 'control_id'} dir={violationCtl.sortDir} onSort={violationCtl.toggleSort} />
                    <SortHeader label="Severity" column="severity" active={violationCtl.sortKey === 'severity'} dir={violationCtl.sortDir} onSort={violationCtl.toggleSort} />
                    <th>Explanation</th>
                  </tr>
                </thead>
                <tbody>
                  {violationCtl.visible.map((v) => (
                    <tr key={v.violation_id} className={violationCtl.isHighlighted(v) ? 'highlighted' : ''}>
                      <td className="mono">{v.violation_id}</td>
                      <td className="mono">{v.log_id}</td>
                      <td>{v.violation_type.replace(/_/g, ' ')}</td>
                      <td className="mono">{v.control_id}</td>
                      <td>{v.severity}</td>
                      <td className="table-truncate" title={v.explanation}>
                        {v.explanation}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {violationCtl.visible.length < violationCtl.totalFiltered && (
              <button type="button" className="link-btn table-more" onClick={violationCtl.showMore}>
                Show more ({violationCtl.totalFiltered - violationCtl.visible.length} remaining)
              </button>
            )}
          </div>

          <div className="glass-panel tab-panel panel-pad">
            <div className="panel-title">Q&amp;A Pairs</div>
            <div className="table-toolbar">
              <input
                type="text"
                className="wizard-input table-search"
                placeholder="Search Q&A pairs…"
                value={qaCtl.query}
                onChange={(e) => qaCtl.setQuery(e.target.value)}
              />
              <span className="table-count">
                {qaCtl.totalFiltered} / {qaCtl.totalAll}
              </span>
            </div>
            <div className="data-table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <SortHeader label="QA ID" column="qa_id" active={qaCtl.sortKey === 'qa_id'} dir={qaCtl.sortDir} onSort={qaCtl.toggleSort} />
                    <th>Question</th>
                    <th>Answer</th>
                    <SortHeader label="Grounding" column="grounding" active={qaCtl.sortKey === 'grounding'} dir={qaCtl.sortDir} onSort={qaCtl.toggleSort} />
                  </tr>
                </thead>
                <tbody>
                  {qaCtl.visible.map((q) => (
                    <tr key={q.qa_id} className={qaCtl.isHighlighted(q) ? 'highlighted' : ''}>
                      <td className="mono">{q.qa_id}</td>
                      <td className="table-truncate" title={q.question}>
                        {q.question}
                      </td>
                      <td className="table-truncate" title={q.answer}>
                        {q.answer}
                      </td>
                      <td>{q.grounding}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {qaCtl.visible.length < qaCtl.totalFiltered && (
              <button type="button" className="link-btn table-more" onClick={qaCtl.showMore}>
                Show more ({qaCtl.totalFiltered - qaCtl.visible.length} remaining)
              </button>
            )}
          </div>
        </>
      )}
    </div>
  );
}
