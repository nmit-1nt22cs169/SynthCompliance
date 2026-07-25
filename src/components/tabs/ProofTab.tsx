import { Badge } from '../Badge';
import { StaleBanner } from '../StaleBanner';
import { deriveRetrainTrend } from '../../lib/derive';
import type { ConfusionMatrix, ValidationReport } from '../../types';

interface ProofTabProps {
  report: ValidationReport;
  accent: string;
  jobActive?: boolean;
}

interface Bar {
  label: string;
  sublabel?: string;
  value: number;
  color: string;
  best?: boolean;
}

// Mirrors OverviewTab.tsx's riskColor() — diagonal (correct) cells tinted green, off-diagonal
// (errors) tinted red, alpha scaled by each cell's share of the eval set.
function matrixCellColor(value: number, total: number, correct: boolean): string {
  if (value === 0 || total === 0) return 'transparent';
  const t = Math.min(value / total, 1);
  return correct ? `rgba(62, 207, 142, ${0.1 + t * 0.6})` : `rgba(224, 85, 90, ${0.1 + t * 0.6})`;
}

function ConfusionMatrixTable({ title, matrix }: { title: string; matrix: ConfusionMatrix }) {
  const total = matrix.tp + matrix.fp + matrix.tn + matrix.fn;
  return (
    <div className="matrix-wrap">
      <div className="proof-desc" style={{ marginBottom: 4, fontWeight: 600 }}>{title}</div>
      <table className="data-table matrix-table confusion-matrix-table">
        <thead>
          <tr>
            <th></th>
            <th>Predicted violation</th>
            <th>Predicted normal</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>Actual violation</td>
            <td className="matrix-cell" style={{ background: matrixCellColor(matrix.tp, total, true) }}>{matrix.tp}</td>
            <td className="matrix-cell" style={{ background: matrixCellColor(matrix.fn, total, false) }}>{matrix.fn}</td>
          </tr>
          <tr>
            <td>Actual normal</td>
            <td className="matrix-cell" style={{ background: matrixCellColor(matrix.fp, total, false) }}>{matrix.fp}</td>
            <td className="matrix-cell" style={{ background: matrixCellColor(matrix.tn, total, true) }}>{matrix.tn}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function ProofTab({ report, accent, jobActive }: ProofTabProps) {
  const tstr = report.tstr_metrics;
  const golden = report.golden_set_fidelity;
  const baseline = tstr?.baseline_rare_recall ?? 0;
  const trained = tstr?.synthetic_trained_rare_recall ?? 0;
  const transformerModels = tstr?.transformer_models ?? [];
  const bestModel = tstr?.transformer_best_model;

  const bars: Bar[] = [
    { label: 'Rule baseline', value: baseline, color: 'var(--amber)' },
    { label: 'Logistic reg.', sublabel: 'synthetic-trained', value: trained, color: accent },
  ];
  if (tstr?.rule_strict_rare_recall != null) {
    bars.push({ label: 'Rule (strict)', sublabel: 'stricter rare-class def.', value: tstr.rule_strict_rare_recall, color: '#c98a2e' });
  }
  if (tstr?.lr_strict_rare_recall != null) {
    bars.push({ label: 'LR (strict)', sublabel: 'stricter rare-class def.', value: tstr.lr_strict_rare_recall, color: '#5f5fd6' });
  }
  for (const m of transformerModels) {
    const short = m.transformer_model.replace('microsoft/', '').replace('-base-uncased', '').replace('-v3-base', '-v3');
    bars.push({
      label: short,
      sublabel: m.transformer_eval_pack ? `${m.transformer_train_pack}→${m.transformer_eval_pack}` : undefined,
      value: m.transformer_rare_recall ?? 0,
      color: short.includes('deberta') ? '#7c5cff' : '#3b82f6',
      best: m.transformer_model === bestModel,
    });
  }

  const retrainHistory = tstr?.retrain_history ?? [];
  const retrainTrend = retrainHistory.length >= 2 ? deriveRetrainTrend(retrainHistory) : null;

  const maxRecall = Math.max(...bars.map((b) => b.value), 0.01);
  const bestValue = Math.max(...bars.map((b) => b.value));
  const headlineLift = bestValue - baseline;
  const chartW = 520 + Math.max(0, bars.length - 2) * 120;
  const chartH = 240;
  const padL = 48;
  const padB = 52;
  const padT = 24;
  const step = 120;
  const barW = 80;
  const plotH = chartH - padB - padT;
  const plotBottom = padT + plotH;
  const labelY = plotBottom + 20;
  const sublabelY = plotBottom + 36;

  return (
    <div>
      {jobActive && <StaleBanner />}
      <div className="proof-grid tab-panel">
        <div className="glass-panel proof-panel">
          <div className="panel-title">TSTR — Rare-Class Recall Lift</div>
          <p className="proof-desc">
            {tstr?.transformer_best_model
              ? `4-way comparison on a leakage-safe pack split (train ${transformerModels[0]?.transformer_train_pack ?? 'SOX'} → eval ${transformerModels[0]?.transformer_eval_pack ?? 'GDPR'}, no shared violation types). ` +
                `Logistic regression trained on oversampled synthetic SOX data (${((tstr?.train_violation_rate ?? 0) * 100).toFixed(0)}% violation rate); ` +
                `transformers trained on the same SOX split, all evaluated on the held-out GDPR realistic-ratio set (${((transformerModels[0]?.transformer_eval_violation_rate ?? tstr?.eval_violation_rate ?? 0) * 100).toFixed(1)}% violation rate).`
              : `Logistic regression trained on oversampled synthetic data (${((tstr?.train_violation_rate ?? 0) * 100).toFixed(0)}% violation rate), ` +
                `evaluated on a realistic-ratio hold-out set (${((tstr?.eval_violation_rate ?? 0) * 100).toFixed(1)}% violation rate). ` +
                `Run scripts/train_transformers.py on the GPU cluster to add the DistilBERT + DeBERTa bars.`}
          </p>
          <svg viewBox={`0 0 ${chartW} ${chartH}`} className="proof-chart">
            {bars.map((b, i) => {
              const x = padL + i * step;
              // A real 0% measurement should still read as "measured zero," not "nothing
              // rendered" — a thin sliver keeps the bar (and its label) visible and legible.
              const h = Math.max((b.value / maxRecall) * plotH, 3);
              const y = padT + plotH - h;
              return (
                <g key={b.label}>
                  <rect x={x} y={y} width={barW} height={h} rx={8} fill={b.color} opacity={0.9} />
                  <text x={x + barW / 2} y={y - 8} textAnchor="middle" fontSize={13} fill="var(--text-primary)" fontWeight="600">
                    {(b.value * 100).toFixed(0)}%
                  </text>
                  <text x={x + barW / 2} y={labelY} textAnchor="middle" fontSize={12} fill="var(--text-secondary)">
                    {b.label}
                  </text>
                  {b.sublabel && (
                    <text x={x + barW / 2} y={sublabelY} textAnchor="middle" fontSize={10} fill="#9a9aa0">
                      {b.sublabel}
                    </text>
                  )}
                </g>
              );
            })}
            <line x1={padL - 8} y1={padT + plotH} x2={chartW - 20} y2={padT + plotH} stroke="rgba(0,0,0,0.12)" />
          </svg>
          <div className="proof-metrics">
            <div className="proof-metric">
              <span className="proof-metric-label">Recall lift (best vs rule)</span>
              <span className="proof-metric-value">
                {headlineLift >= 0 ? '+' : ''}{(headlineLift * 100).toFixed(0)} pts
              </span>
            </div>
            <div className="proof-metric">
              <span className="proof-metric-label">Train / Eval size</span>
              <span className="proof-metric-value">
                {tstr?.transformer_best_model
                  ? `${transformerModels[0]?.transformer_train_size ?? tstr?.train_size ?? '—'} / ${transformerModels[0]?.transformer_eval_size ?? tstr?.eval_size ?? '—'}`
                  : `${tstr?.train_size ?? '—'} / ${tstr?.eval_size ?? '—'}`}
              </span>
            </div>
            <div className="proof-metric">
              <span className="proof-metric-label">Best model</span>
              <span className="proof-metric-value">
                {tstr?.transformer_best_model
                  ? tstr.transformer_best_model.replace('microsoft/', '').replace('-base-uncased', '').replace('-v3-base', '-v3')
                  : tstr?.model ?? 'LogisticRegression'}
              </span>
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

      {tstr?.confusion_matrix_after && (
        <div className="glass-panel panel-pad tab-panel">
          <div className="panel-title">
            {tstr.retrained
              ? `Retrain Impact — Before vs After (v${tstr.model_version}, ${tstr.cumulative_train_size?.toLocaleString()} cumulative rows)`
              : `Persisted Model — Current State (v${tstr.model_version}, ${tstr.cumulative_train_size?.toLocaleString()} cumulative rows)`}
          </div>
          <div className="proof-grid">
            {tstr.retrained ? (
              tstr.confusion_matrix_before ? (
                <ConfusionMatrixTable title="Before this retrain" matrix={tstr.confusion_matrix_before} />
              ) : (
                <div className="proof-desc">First retrain — no prior persisted model to compare.</div>
              )
            ) : (
              <div className="proof-desc">
                Recall held steady or improved this run, so retraining didn't fire — showing the persisted
                model's state from its last retrain instead.
              </div>
            )}
            <ConfusionMatrixTable title={tstr.retrained ? 'After this retrain' : 'Current persisted model'} matrix={tstr.confusion_matrix_after} />
          </div>
          {tstr.metrics_after && (
            <div className="proof-metrics" style={{ marginTop: 16 }}>
              {(['precision', 'recall', 'f1', 'accuracy'] as const).map((key) => {
                const after = tstr.metrics_after![key];
                const before = tstr.metrics_before?.[key];
                const delta = before != null ? after - before : null;
                return (
                  <div className="proof-metric" key={key}>
                    <span className="proof-metric-label">{key}</span>
                    <span className="proof-metric-value">
                      {before != null ? `${before.toFixed(2)} → ` : ''}
                      {after.toFixed(2)}
                      {delta != null ? ` (${delta >= 0 ? '+' : ''}${delta.toFixed(2)})` : ''}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {retrainTrend && (
        <div className="glass-panel panel-pad tab-panel">
          <div className="panel-title">Retrain Trend — Recall Across Model Versions</div>
          <p className="proof-desc">
            Recall of the persisted classifier at each retrain, evaluated on that run's eval set —
            shows whether the growing cumulative training set is actually improving the model over time.
          </p>
          <svg viewBox={`0 0 ${retrainTrend.w} ${retrainTrend.h}`} style={{ width: '100%', height: 200, overflow: 'visible' }}>
            <path d={retrainTrend.areaPath} fill={accent} opacity={0.14} />
            <path d={retrainTrend.linePath} fill="none" stroke={accent} strokeWidth={2.5} />
            {retrainTrend.points.map((p, i) => (
              <g key={i}>
                <circle cx={p.x} cy={p.y} r={4} fill={accent} stroke="var(--surface-hole)" strokeWidth={2} />
                <text x={p.x} y={p.labelY} fontSize={11} fill="var(--text-tertiary)" textAnchor="middle">
                  {p.durationLabel}
                </text>
                <text x={p.x} y={retrainTrend.axisY} fontSize={11} fill="var(--text-secondary)" textAnchor="middle">
                  {p.shortName}
                </text>
              </g>
            ))}
          </svg>
        </div>
      )}
    </div>
  );
}
