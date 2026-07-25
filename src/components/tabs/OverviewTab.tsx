import { useMemo } from 'react';
import { Breadcrumb } from '../Breadcrumb';
import { Badge, SeverityBadge } from '../Badge';
import { InfoTip } from '../InfoTip';
import { StaleBanner } from '../StaleBanner';
import {
  deriveCoverage,
  deriveKpis,
  deriveRiskMatrix,
  deriveSeverityCounts,
  deriveValidators,
  deriveWeightBars
} from '../../lib/derive';
import type { AuditLog, DataTable, ValidationReport, Violation } from '../../types';

interface OverviewTabProps {
  report: ValidationReport;
  auditLogs: AuditLog[];
  violations: Violation[];
  accent: string;
  jobActive?: boolean;
  onJump?: (table: DataTable, id: string) => void;
}

function riskColor(rate: number): string {
  if (rate === 0) return 'transparent';
  const t = Math.min(rate, 100) / 100;
  return `rgba(224, 85, 90, ${0.1 + t * 0.6})`;
}

export function OverviewTab({ report, auditLogs, violations, accent, jobActive, onJump }: OverviewTabProps) {
  const kpis = deriveKpis(report, accent);
  const { coverage, total, donutGradient } = deriveCoverage(report, accent);
  const validators = deriveValidators(report);
  const severityCounts = useMemo(() => deriveSeverityCounts(violations), [violations]);
  const weightBars = deriveWeightBars(report.feedback_loop?.next_violation_type_weights);
  const riskMatrix = useMemo(() => deriveRiskMatrix(auditLogs, violations), [auditLogs, violations]);

  const violationRatio = total > 0
    ? ((report.validators.scenario_coverage.violation / total) * 100).toFixed(1)
    : '0.0';
  const recallLift = report.tstr_metrics ? ((report.tstr_metrics.recall_lift ?? 0) * 100).toFixed(0) : '0';
  const goldenScore = report.golden_set_fidelity?.label_fidelity_score?.toFixed(1) ?? '0.0';
  const repairedRows = report.repair_log?.repaired_log_ids ?? [];

  const feedback = report.feedback_loop;
  const proofHighlights = [
    {
      label: 'Rare-class recall lift',
      value: `${recallLift}%`,
      detail: 'How much better a model trained on synthetic data is at catching rare violations vs. a simple rule-based check.'
    },
    {
      label: 'Golden fidelity',
      value: `${goldenScore}%`,
      detail: 'How closely generated records match hand-authored reference examples.'
    },
    {
      label: 'Repaired rows',
      value: `${repairedRows.length}`,
      detail: 'Rows the validator found invalid and auto-corrected before this run finished.'
    },
    {
      label: 'Violation ratio',
      value: `${violationRatio}%`,
      detail: 'Share of logs that are violations — deliberately higher than real-world rates so the model has enough rare cases to learn from.'
    }
  ];

  return (
    <div>
      {jobActive && <StaleBanner />}
      <Breadcrumb stages={report.pipeline_stages} />

      <div className="glass-panel tab-panel panel-pad">
        <div className="panel-title">Dataset Targets — Actual vs Target</div>
        <div className="kpi-grid">
          {kpis.map((k) => (
            <div className="kpi-card" key={k.label}>
              <div className="kpi-value">
                {k.actual}
                <span className="kpi-target"> / {k.target}</span>
              </div>
              <div className="kpi-bar-track">
                <div className="kpi-bar-target-line" />
                <div
                  className="kpi-bar"
                  style={{
                    height: `${k.barHeight}px`,
                    background: k.barColor,
                    boxShadow: `0 4px 12px -4px ${k.barColor}`
                  }}
                />
              </div>
              <div className="kpi-label">{k.label}</div>
            </div>
          ))}
        </div>
      </div>

      <div className="glass-panel tab-panel panel-pad">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Violation Severity Breakdown
        </div>
        <div className="severity-pill-row">
          <div className="severity-pill-item">
            <SeverityBadge severity="critical" />
            <span className="severity-pill-count">{severityCounts.critical}</span>
          </div>
          <div className="severity-pill-item">
            <SeverityBadge severity="high" />
            <span className="severity-pill-count">{severityCounts.high}</span>
          </div>
          <div className="severity-pill-item">
            <SeverityBadge severity="medium" />
            <span className="severity-pill-count">{severityCounts.medium}</span>
          </div>
          <div className="severity-pill-item">
            <SeverityBadge severity="low" />
            <span className="severity-pill-count">{severityCounts.low}</span>
          </div>
        </div>
      </div>

      <div className="glass-panel tab-panel panel-pad">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Adaptive Feedback Loop
          <InfoTip text="Findings from each run are stored and bias what the next run generates more of." />
        </div>
        <div className="validation-detail" style={{ marginBottom: 12 }}>
          Newly detected patterns are stored after each run and reweighted in the next generation pass.
        </div>
        <div className="kpi-grid">
          <div className="kpi-card">
            <div className="kpi-value">{feedback?.new_violation_patterns?.length ? feedback.new_violation_patterns.join(', ') : 'none yet'}</div>
            <div className="kpi-label">New patterns detected</div>
            <div className="validation-detail">The next run will bias generation toward these violation types.</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-value">{feedback?.improved ? 'improving' : 'monitoring'}</div>
            <div className="kpi-label">
              TSTR feedback state
              <InfoTip text="'Improving' = this run's recall lift beat the previous run. 'Monitoring' = not yet — still collecting runs." />
            </div>
            <div className="validation-detail">Tracks whether the latest run improved recall lift versus the previous run.</div>
          </div>
        </div>
        {weightBars.length > 0 && (
          <div className="weight-bar-list">
            <div className="wizard-label" style={{ marginBottom: 8, marginTop: 8 }}>
              Next-run violation-type weights
            </div>
            {weightBars.map((w) => (
              <div className="activity-bar-row" key={w.label}>
                <span className="activity-bar-label">{w.label}</span>
                <div className="activity-bar-track">
                  <div className="activity-bar-fill" style={{ width: `${w.pct}%`, background: 'var(--amber)' }} />
                </div>
                <span className="activity-bar-count">{w.weight.toFixed(2)}x</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="glass-panel tab-panel panel-pad">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Key Proof Metrics
          <InfoTip text="TSTR = Train Synthetic, Test Real: prove synthetic data is useful by training a model on it and testing against real-world-shaped data." />
        </div>
        <div className="kpi-grid">
          {proofHighlights.map((item) => (
            <div className="kpi-card" key={item.label}>
              <div className="kpi-value">{item.value}</div>
              <div className="kpi-label">{item.label}</div>
              <div className="validation-detail">{item.detail}</div>
            </div>
          ))}
        </div>
        {repairedRows.length > 0 && onJump && (
          <div className="repaired-links">
            {repairedRows.slice(0, 12).map((id) => (
              <button key={id} type="button" className="link-btn repaired-link" onClick={() => onJump('auditLogs', id)}>
                {id}
              </button>
            ))}
          </div>
        )}
      </div>

      {riskMatrix.roles.length > 0 && (
        <div className="glass-panel tab-panel panel-pad">
          <div className="panel-title">
            Risk Matrix — Role × Sensitivity (violation rate %)
            <InfoTip text="% of that role's logs against that sensitivity level which were violations — darker = riskier combination." />
          </div>
          <div className="matrix-wrap">
            <table className="data-table matrix-table">
              <thead>
                <tr>
                  <th>Role</th>
                  {riskMatrix.sensitivities.map((s) => (
                    <th key={s}>{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {riskMatrix.roles.map((role) => (
                  <tr key={role}>
                    <td>{role.replace(/_/g, ' ')}</td>
                    {riskMatrix.sensitivities.map((sensitivity) => {
                      const cell = riskMatrix.cells.find((c) => c.role === role && c.sensitivity === sensitivity);
                      return (
                        <td key={sensitivity} className="matrix-cell" style={{ background: riskColor(cell?.rate ?? 0) }}>
                          {cell && cell.total > 0 ? `${cell.rate}%` : ''}
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

      <div className="overview-row-2">
        <div className="glass-panel donut-panel panel-pad">
          <div className="panel-title">Scenario Coverage</div>
          <div className="donut" style={{ background: donutGradient }}>
            <div className="donut-hole">
              <div className="donut-hole-value">{total}</div>
              <div className="donut-hole-label">total logs</div>
            </div>
          </div>
          <div className="coverage-legend">
            {coverage.map((c) => (
              <div className="coverage-row" key={c.key}>
                <div className="coverage-swatch" style={{ background: c.color }} />
                <span className="coverage-label">{c.label}</span>
                <span className="coverage-count">
                  {c.count} · {c.pct}%
                </span>
              </div>
            ))}
          </div>
        </div>

        <div className="glass-panel panel-pad">
          <div className="panel-title">Validation Status</div>
          {validators.map((v) => (
            <div className="validation-row" key={v.key}>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                <span className="validation-name">{v.name}</span>
                <span className="validation-detail">{v.detail}</span>
              </div>
              <Badge status={v.status} />
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
