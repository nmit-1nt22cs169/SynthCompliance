import type { PipelineStage } from '../types';

interface BreadcrumbProps {
  stages: PipelineStage[];
}

export function Breadcrumb({ stages }: BreadcrumbProps) {
  return (
    <div className="breadcrumb glass-panel">
      {stages.map((s, i) => {
        const cls = s.status === 'running' ? 'current' : s.status === 'completed' ? 'done' : 'upcoming';
        return (
          <div className="breadcrumb-item" key={s.stage}>
            <span className={`breadcrumb-stage ${cls}`}>{s.stage}</span>
            {i < stages.length - 1 && <span className="breadcrumb-arrow">→</span>}
          </div>
        );
      })}
    </div>
  );
}
