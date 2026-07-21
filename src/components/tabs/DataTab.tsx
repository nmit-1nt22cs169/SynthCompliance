import type { AuditLog, QaPair, Violation } from '../../types';

const SAMPLE_SIZE = 8;

interface DataTabProps {
  auditLogs: AuditLog[];
  violations: Violation[];
  qaPairs: QaPair[];
}

export function DataTab({ auditLogs, violations, qaPairs }: DataTabProps) {
  return (
    <div className="data-grid">
      <div className="glass-panel data-panel">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Sample Audit Logs
        </div>
        <pre className="json-block json-audit">{JSON.stringify(auditLogs.slice(0, SAMPLE_SIZE), null, 2)}</pre>
      </div>
      <div className="glass-panel data-panel">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Sample Violations
        </div>
        <pre className="json-block json-violations">{JSON.stringify(violations.slice(0, SAMPLE_SIZE), null, 2)}</pre>
      </div>
      <div className="glass-panel data-panel">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Sample Q&amp;A Pairs
        </div>
        <pre className="json-block json-qa">{JSON.stringify(qaPairs.slice(0, SAMPLE_SIZE), null, 2)}</pre>
      </div>
    </div>
  );
}
