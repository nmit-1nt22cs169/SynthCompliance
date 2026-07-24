interface HeaderProps {
  refreshing: boolean;
  runId?: string | null;
  jobActive?: boolean;
}

export function Header({ refreshing, runId, jobActive }: HeaderProps) {
  return (
    <div className="header-bar glass-panel">
      <div className="header-titles">
        <div className="header-title">SynthCompliance Dashboard</div>
        <div className="header-subtitle">
          {jobActive
            ? 'Live pipeline run in progress…'
            : runId
              ? `Live dataset · ${runId}`
              : 'Waiting for pipeline output — run a job from Pipeline tab'}
        </div>
      </div>
      <div className="header-right">
        {refreshing && <div className="refreshing-label">Syncing live data…</div>}
        <div className={`live-pill${jobActive ? ' live-pill-active' : ''}`}>
          <div className="live-dot" />
          <span className="live-label">{jobActive ? 'Running' : 'Live'}</span>
        </div>
      </div>
    </div>
  );
}
