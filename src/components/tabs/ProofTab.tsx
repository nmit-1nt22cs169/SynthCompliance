import { Badge } from '../Badge';
import type { ValidationReport } from '../../types';

interface ProofTabProps {
  report: ValidationReport;
  accent: string;
}

export function ProofTab({ report, accent }: ProofTabProps) {
  const tstr = report.tstr_metrics;
  const golden = report.golden_set_fidelity;
  const baseline = tstr?.baseline_rare_recall ?? 0;
  const trained = tstr?.synthetic_trained_rare_recall ?? 0;
  const maxRecall = Math.max(baseline, trained, 0.01);
  const chartW = 520;
  const chartH = 220;
  const padL = 48;
  const padB = 36;
  const padT = 24;
  const barW = 80;
  const plotH = chartH - padB - padT;

  const bars = [
    { label: 'Baseline', value: baseline, color: 'var(--amber)' },
    { label: 'Synthetic-trained', value: trained, color: accent }
  ];

  return (
    <div className="proof-grid">
      <div className="glass-panel proof-panel">
        <div className="panel-title">TSTR — Rare-Class Recall Lift</div>
        <p className="proof-desc">
          Logistic regression trained on oversampled synthetic data ({((tstr?.train_violation_rate ?? 0) * 100).toFixed(0)}% violation rate),
          evaluated on a realistic-ratio hold-out set ({((tstr?.eval_violation_rate ?? 0) * 100).toFixed(1)}% violation rate).
        </p>
        <svg viewBox={`0 0 ${chartW} ${chartH}`} className="proof-chart">
          {bars.map((b, i) => {
            const x = padL + i * 180;
            const h = (b.value / maxRecall) * plotH;
            const y = padT + plotH - h;
            return (
              <g key={b.label}>
                <rect x={x} y={y} width={barW} height={h} rx={8} fill={b.color} opacity={0.9} />
                <text x={x + barW / 2} y={y - 8} textAnchor="middle" fontSize={13} fill="var(--text-primary)" fontWeight="600">
                  {(b.value * 100).toFixed(0)}%
                </text>
                <text x={x + barW / 2} y={chartH - 10} textAnchor="middle" fontSize={12} fill="var(--text-secondary)">
                  {b.label}
                </text>
              </g>
            );
          })}
          <line x1={padL - 8} y1={padT + plotH} x2={chartW - 20} y2={padT + plotH} stroke="rgba(0,0,0,0.12)" />
        </svg>
        <div className="proof-metrics">
          <div className="proof-metric">
            <span className="proof-metric-label">Recall lift</span>
            <span className="proof-metric-value">+{((tstr?.recall_lift ?? 0) * 100).toFixed(0)} pts</span>
          </div>
          <div className="proof-metric">
            <span className="proof-metric-label">Train / Eval size</span>
            <span className="proof-metric-value">
              {tstr?.train_size ?? '—'} / {tstr?.eval_size ?? '—'}
            </span>
          </div>
          <div className="proof-metric">
            <span className="proof-metric-label">Model</span>
            <span className="proof-metric-value">{tstr?.model ?? 'LogisticRegression'}</span>
          </div>
          <Badge status={tstr?.status === 'pass' ? 'pass' : 'warn'} />
        </div>
      </div>

      <div className="glass-panel proof-panel">
        <div className="panel-title">Golden-Set Fidelity</div>
        <p className="proof-desc">
          Third proof layer: label triple match vs taxonomy golden references + statistical distribution alignment.
        </p>
        <div className="fidelity-scores">
          <div className="fidelity-card">
            <div className="fidelity-value">{(golden?.label_fidelity_score ?? 0).toFixed(1)}%</div>
            <div className="fidelity-label">Label fidelity</div>
            <div className="fidelity-sub">
              {golden?.classes_matched ?? 0} / {golden?.classes_total ?? 16} violation classes matched
            </div>
          </div>
          <div className="fidelity-card">
            <div className="fidelity-value">{(golden?.statistical_fidelity_score ?? 0).toFixed(1)}%</div>
            <div className="fidelity-label">Statistical fidelity</div>
            <div className="fidelity-sub">Max field deviation {(golden?.max_field_deviation_pct ?? 0).toFixed(1)}%</div>
          </div>
        </div>
        <div className="proof-metrics" style={{ marginTop: 16 }}>
          <div className="proof-metric">
            <span className="proof-metric-label">Golden seeds matched</span>
            <span className="proof-metric-value">
              {golden?.matched_seeds ?? 0} / {golden?.total_seeds ?? 0}
            </span>
          </div>
          <Badge status={golden?.status === 'pass' ? 'pass' : golden?.status === 'warn' ? 'warn' : 'fail'} />
        </div>
      </div>
    </div>
  );
}
