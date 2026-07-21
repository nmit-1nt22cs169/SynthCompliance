import { Fragment } from 'react';
import { Badge } from '../Badge';
import { deriveFlaggedRows, deriveValidators } from '../../lib/derive';
import type { ValidationReport } from '../../types';

interface ValidationTabProps {
  report: ValidationReport;
}

export function ValidationTab({ report }: ValidationTabProps) {
  const validators = deriveValidators(report);
  const flaggedRows = deriveFlaggedRows(report);

  return (
    <div>
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

      <div className="glass-panel" style={{ padding: '24px 28px' }}>
        <div className="panel-title" style={{ marginBottom: 16 }}>
          Flagged Rows
        </div>
        <div className="flagged-table">
          <div className="flagged-header">Validator</div>
          <div className="flagged-header">Row / Violation ID</div>
          <div className="flagged-header">Reason</div>
          {flaggedRows.map((f, i) => (
            <Fragment key={i}>
              <div className="flagged-cell validator">{f.validator}</div>
              <div className="flagged-cell id">{f.id}</div>
              <div className="flagged-cell reason">{f.reason}</div>
            </Fragment>
          ))}
        </div>
      </div>
    </div>
  );
}
