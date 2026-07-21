import type { PipelineStage } from '../types';

const STAGE_NAMES = [
  'Policy Templates',
  'Event Generator',
  'Scenario Composer',
  'Regulation Annotator',
  'NeMo Curator',
  'Output Datasets'
];

interface BreadcrumbProps {
  stages: PipelineStage[];
}

export function Breadcrumb({ stages }: BreadcrumbProps) {
  let lastCompletedIdx = -1;
  stages.forEach((s, i) => {
    if (s.status === 'completed') lastCompletedIdx = i;
  });

  return (
    <div className="breadcrumb glass-panel">
      {STAGE_NAMES.map((name, i) => {
        const cls = i === lastCompletedIdx ? 'current' : i < lastCompletedIdx ? 'done' : 'upcoming';
        return (
          <div className="breadcrumb-item" key={name}>
            <span className={`breadcrumb-stage ${cls}`}>{name}</span>
            {i < STAGE_NAMES.length - 1 && <span className="breadcrumb-arrow">→</span>}
          </div>
        );
      })}
    </div>
  );
}
