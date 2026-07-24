import { exportBundleUrl } from '../../lib/api';
import type { AuditLog, QaPair, Violation } from '../../types';

const PREVIEW_SIZE = 8;

interface DataTabProps {
  auditLogs: AuditLog[];
  violations: Violation[];
  qaPairs: QaPair[];
}

export function DataTab({ auditLogs, violations, qaPairs }: DataTabProps) {
  const hasLiveData = auditLogs.length > 0 || violations.length > 0 || qaPairs.length > 0;

  return (
    <div>
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
        <div className="data-grid">
          <div className="glass-panel data-panel">
            <div className="panel-title" style={{ marginBottom: 12 }}>
              Latest Audit Logs
            </div>
            <pre className="json-block json-audit">{JSON.stringify(auditLogs.slice(0, PREVIEW_SIZE), null, 2)}</pre>
          </div>
          <div className="glass-panel data-panel">
            <div className="panel-title" style={{ marginBottom: 12 }}>
              Latest Violations
            </div>
            <pre className="json-block json-violations">{JSON.stringify(violations.slice(0, PREVIEW_SIZE), null, 2)}</pre>
          </div>
          <div className="glass-panel data-panel">
            <div className="panel-title" style={{ marginBottom: 12 }}>
              Latest Q&amp;A Pairs
            </div>
            <pre className="json-block json-qa">{JSON.stringify(qaPairs.slice(0, PREVIEW_SIZE), null, 2)}</pre>
          </div>
        </div>
      )}
    </div>
  );
}
