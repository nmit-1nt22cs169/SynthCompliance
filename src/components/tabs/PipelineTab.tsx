import { Badge } from '../Badge';
import { deriveLineChart } from '../../lib/derive';
import type { ValidationReport } from '../../types';

interface PipelineTabProps {
  report: ValidationReport;
  accent: string;
}

export function PipelineTab({ report, accent }: PipelineTabProps) {
  const lineChart = deriveLineChart(report);

  return (
    <div>
      <div className="glass-panel tab-panel" style={{ padding: '24px 28px' }}>
        <div className="panel-title">Stage Duration Trend</div>
        <svg
          viewBox={`0 0 ${lineChart.w} ${lineChart.h}`}
          style={{ width: '100%', height: 200, overflow: 'visible' }}
        >
          <path d={lineChart.areaPath} fill={accent} opacity={0.14} />
          <path d={lineChart.linePath} fill="none" stroke={accent} strokeWidth={2.5} />
          {lineChart.points.map((p, i) => (
            <g key={i}>
              <circle cx={p.x} cy={p.y} r={4} fill={accent} stroke="#f4f5f8" strokeWidth={2} />
              <text x={p.x} y={p.labelY} fontSize={11} fill="#8e8e93" textAnchor="middle">
                {p.durationLabel}
              </text>
              <text x={p.x} y={lineChart.axisY} fontSize={11} fill="#6e6e73" textAnchor="middle">
                {p.shortName}
              </text>
            </g>
          ))}
        </svg>
      </div>

      <div className="glass-panel" style={{ padding: '24px 28px' }}>
        <div className="panel-title" style={{ marginBottom: 16 }}>
          Pipeline Flow
        </div>
        {report.pipeline_stages.map((s) => (
          <div className="pipeline-row" key={s.stage}>
            <span className="pipeline-stage-name">{s.stage}</span>
            <div className="pipeline-row-right">
              <span className="pipeline-duration">{s.duration_ms}ms</span>
              <Badge status={s.status} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
