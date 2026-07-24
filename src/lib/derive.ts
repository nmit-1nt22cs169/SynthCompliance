import type { ValidationReport, ValidatorStatus } from '../types';

export interface Kpi {
  label: string;
  actual: number;
  target: number;
  barHeight: number;
  barColor: string;
}

export function deriveKpis(report: ValidationReport, accent: string): Kpi[] {
  const defs = [
    { label: 'Audit Logs generated', actual: report.dataset_actual.audit_logs, target: report.dataset_targets.audit_logs },
    { label: 'Violations labelled', actual: report.dataset_actual.violations, target: report.dataset_targets.violations },
    { label: 'Q&A pairs', actual: report.dataset_actual.qa_pairs, target: report.dataset_targets.qa_pairs },
    {
      label: 'Investigation summaries',
      actual: report.dataset_actual.investigation_summaries,
      target: report.dataset_targets.investigation_summaries
    }
  ];
  return defs.map((k) => {
    const ratio = k.actual / k.target;
    const barHeight = Math.round(Math.min(ratio, 1.15) * 100);
    const barColor = ratio >= 1 ? 'var(--green-dark)' : ratio >= 0.9 ? accent : 'var(--amber)';
    return { ...k, barHeight, barColor };
  });
}

export interface CoverageSlice {
  key: string;
  label: string;
  count: number;
  pct: number;
  color: string;
}

export function deriveCoverage(report: ValidationReport, accent: string) {
  const covColors: Record<string, string> = {
    normal: 'var(--green-dark)',
    suspicious: 'var(--amber)',
    violation: 'var(--red)',
    false_positive: accent
  };
  const entries = Object.entries(report.validators.scenario_coverage) as [string, number][];
  const total = entries.reduce((sum, [, v]) => sum + v, 0);
  let cursor = 0;
  const gradientParts: string[] = [];
  const coverage: CoverageSlice[] = entries.map(([key, count]) => {
    const pct = Math.round((count / total) * 100);
    const start = cursor;
    cursor += pct;
    gradientParts.push(`${covColors[key]} ${start}% ${cursor}%`);
    return {
      key,
      label: key.replace('_', ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      count,
      pct,
      color: covColors[key]
    };
  });
  return { coverage, total, donutGradient: `conic-gradient(${gradientParts.join(', ')})` };
}

export interface ValidatorSummary {
  key: string;
  name: string;
  detail: string;
  status: ValidatorStatus;
}

const VALIDATOR_NAMES: Record<string, string> = {
  schema_validity: 'Schema Validity',
  pii_leakage: 'PII Leakage',
  duplicate_check: 'Duplicate Check',
  label_alignment: 'Label Alignment',
  golden_set_fidelity: 'Golden-Set Fidelity'
};

export function deriveValidators(report: ValidationReport): ValidatorSummary[] {
  const base = Object.entries(VALIDATOR_NAMES).map(([key, name]) => {
    if (key === 'golden_set_fidelity') {
      const g = report.golden_set_fidelity;
      const detail = g
        ? `label ${g.label_fidelity_score.toFixed(1)}% · stat ${g.statistical_fidelity_score.toFixed(1)}%`
        : 'not computed';
      const status = (g?.status as ValidatorStatus) ?? 'warn';
      return { key, name, detail, status };
    }
    let detail: string;
    let status: ValidatorStatus;
    if (key === 'pii_leakage') {
      const v = report.validators.pii_leakage;
      detail = `${v.actual_detections} detected / target ${v.target_detections}`;
      status = v.status;
    } else if (key === 'duplicate_check') {
      const v = report.validators.duplicate_check;
      detail = `${(v.actual_rate * 100).toFixed(1)}% / max ${(v.target_max_rate * 100).toFixed(0)}%`;
      status = v.status;
    } else if (key === 'schema_validity') {
      const v = report.validators.schema_validity;
      detail = `${(v.actual_pass_rate * 100).toFixed(1)}% / target ${(v.target_pass_rate * 100).toFixed(0)}%`;
      status = v.status;
    } else {
      const v = report.validators.label_alignment;
      detail = `${(v.actual_pass_rate * 100).toFixed(1)}% / target ${(v.target_pass_rate * 100).toFixed(0)}%`;
      status = v.status;
    }
    return { key, name, detail, status };
  });
  return base;
}

export interface FlaggedRow {
  validator: string;
  id: string;
  reason: string;
}

export function deriveFlaggedRows(report: ValidationReport): FlaggedRow[] {
  const rows: FlaggedRow[] = [];
  report.validators.schema_validity.flagged.forEach((f) =>
    rows.push({ validator: 'Schema Validity', id: f.log_id, reason: `${f.field}: ${f.issue}` })
  );
  report.validators.pii_leakage.flagged.forEach((f) =>
    rows.push({ validator: 'PII Leakage', id: f.log_id, reason: `${f.entity} detected — ${f.value_redacted}` })
  );
  report.validators.duplicate_check.flagged.forEach((f) =>
    rows.push({
      validator: 'Duplicate Check',
      id: f.log_id,
      reason: `${(f.similarity * 100).toFixed(0)}% similar to ${f.duplicate_of}`
    })
  );
  report.validators.label_alignment.flagged.forEach((f) =>
    rows.push({ validator: 'Label Alignment', id: f.violation_id, reason: f.issue })
  );
  return rows;
}

export interface LineChartPoint {
  x: number;
  y: number;
  labelY: number;
  shortName: string;
  durationLabel: string;
}

export interface LineChart {
  w: number;
  h: number;
  linePath: string;
  areaPath: string;
  points: LineChartPoint[];
  axisY: number;
}

const STAGE_SHORT: Record<string, string> = {
  'Policy Templates': 'Policy',
  'Event Generator': 'Events',
  'Scenario Composer': 'Scenario',
  'Regulation Annotator': 'Annotator',
  'NeMo Curator': 'Curator',
  'Output Datasets': 'Output',
  'Log Generator': 'Generator',
  'Validator': 'Validator',
  'Repair Loop': 'Repair',
  'TSTR Copilot': 'TSTR'
};

export function deriveLineChart(report: ValidationReport): LineChart {
  const w = 640;
  const h = 200;
  const padL = 20;
  const padR = 20;
  const padT = 30;
  const padB = 40;
  const values = report.pipeline_stages.map((s) => s.duration_ms);
  const max = Math.max(...values);
  const n = values.length;
  const stepX = (w - padL - padR) / (n - 1);
  const plotBottom = h - padB;
  const points: LineChartPoint[] = values.map((v, i) => {
    const x = padL + i * stepX;
    const y = padT + (plotBottom - padT) * (1 - v / max);
    return {
      x: +x.toFixed(1),
      y: +y.toFixed(1),
      shortName: STAGE_SHORT[report.pipeline_stages[i].stage] || report.pipeline_stages[i].stage,
      durationLabel: `${v}ms`,
      labelY: +(y - 12).toFixed(1)
    };
  });
  const linePath = 'M ' + points.map((p) => `${p.x},${p.y}`).join(' L ');
  const areaPath = `${linePath} L ${points[n - 1].x},${plotBottom} L ${points[0].x},${plotBottom} Z`;
  return { w, h, linePath, areaPath, points, axisY: h - 12 };
}
