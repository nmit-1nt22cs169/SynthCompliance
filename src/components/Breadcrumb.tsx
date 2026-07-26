import type { PipelineStage } from '../types';

interface BreadcrumbProps {
  stages: PipelineStage[];
}

export function Breadcrumb({ stages }: BreadcrumbProps) {
  return (
    <div className="breadcrumb glass-panel">
      {stages.map((s, i) => {
        // Only ever fed a completed run's static report.pipeline_stages (never live SSE
        // state), so "skipped" here always means "the pipeline finished and chose not to run
        // this stage" — not "not reached yet." Style it like "done", not "upcoming", or a
        // finished run with e.g. a skipped Repair Loop looks like it stalled mid-run.
        const cls = s.status === 'running' ? 'current' : s.status === 'completed' || s.status === 'skipped' ? 'done' : 'upcoming';
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
