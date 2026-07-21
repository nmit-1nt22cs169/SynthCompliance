import { Breadcrumb } from '../Breadcrumb';
import { Badge } from '../Badge';
import { deriveCoverage, deriveKpis, deriveValidators } from '../../lib/derive';
import type { ValidationReport } from '../../types';

interface OverviewTabProps {
  report: ValidationReport;
  accent: string;
}

export function OverviewTab({ report, accent }: OverviewTabProps) {
  const kpis = deriveKpis(report, accent);
  const { coverage, total, donutGradient } = deriveCoverage(report, accent);
  const validators = deriveValidators(report);

  return (
    <div>
      <Breadcrumb stages={report.pipeline_stages} />

      <div className="glass-panel tab-panel" style={{ padding: '24px 28px' }}>
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

      <div className="overview-row-2">
        <div className="glass-panel donut-panel" style={{ padding: '24px 28px' }}>
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

        <div className="glass-panel" style={{ padding: '24px 28px' }}>
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
