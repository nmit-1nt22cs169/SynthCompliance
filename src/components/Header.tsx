interface HeaderProps {
  refreshing: boolean;
  runId?: string | null;
  generatedAt?: string | null;
  jobActive?: boolean;
}

function formatIST(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const time = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(d);
  return `${time} IST`;
}

export function Header({ refreshing, runId, generatedAt, jobActive }: HeaderProps) {
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
        {generatedAt && <div className="header-subtitle">Last run at {formatIST(generatedAt)}</div>}
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
