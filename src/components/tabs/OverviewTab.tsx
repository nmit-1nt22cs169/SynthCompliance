import { Breadcrumb } from '../Breadcrumb';
import { Badge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import { deriveCoverage, deriveKpis, deriveValidators } from '../../lib/derive';
import type { ValidationReport } from '../../types';

interface OverviewTabProps {
  report: ValidationReport;
  accent: string;
  jobActive?: boolean;
}

export function OverviewTab({ report, accent, jobActive }: OverviewTabProps) {
  const kpis = deriveKpis(report, accent);
  const { coverage, total, donutGradient } = deriveCoverage(report, accent);
  const validators = deriveValidators(report);

  const violationRatio = total > 0
    ? ((report.validators.scenario_coverage.violation / total) * 100).toFixed(1)
    : '0.0';
  const recallLift = report.tstr_metrics ? ((report.tstr_metrics.recall_lift ?? 0) * 100).toFixed(0) : '0';
  const goldenScore = report.golden_set_fidelity?.label_fidelity_score?.toFixed(1) ?? '0.0';
  const repairedRows = report.repair_log?.repaired_log_ids?.length ?? 0;

  const feedback = report.feedback_loop;
  const juryHighlights = [
    { label: 'Rare-class recall lift', value: `${recallLift}%`, detail: 'TSTR proof for judges' },
    { label: 'Golden fidelity', value: `${goldenScore}%`, detail: 'Taxonomy match against seeded golden records' },
    { label: 'Repaired rows', value: `${repairedRows}`, detail: 'Rows corrected in the repair loop' },
    { label: 'Violation ratio', value: `${violationRatio}%`, detail: 'Oversampled compliance edge cases' }
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
          Adaptive Feedback Loop
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
            <div className="kpi-label">TSTR feedback state</div>
            <div className="validation-detail">Tracks whether the latest run improved recall lift versus the previous run.</div>
          </div>
        </div>
      </div>

      <div className="glass-panel tab-panel panel-pad">
        <div className="panel-title" style={{ marginBottom: 12 }}>
          Jury Highlights
        </div>
        <div className="kpi-grid">
          {juryHighlights.map((item) => (
            <div className="kpi-card" key={item.label}>
              <div className="kpi-value">{item.value}</div>
              <div className="kpi-label">{item.label}</div>
              <div className="validation-detail">{item.detail}</div>
            </div>
          ))}
        </div>
      </div>

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
