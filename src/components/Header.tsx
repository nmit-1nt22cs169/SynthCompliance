interface HeaderProps {
  refreshing: boolean;
}

export function Header({ refreshing }: HeaderProps) {
  return (
    <div className="header-bar glass-panel">
      <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <div className="header-title">SynthCompliance Dashboard</div>
        <div className="header-subtitle">AI no Kokyū · Synthetic Data Generation Pipeline</div>
      </div>
      <div className="header-right">
        {refreshing && <div className="refreshing-label">Refreshing…</div>}
        <div className="live-pill">
          <div className="live-dot" />
          <span className="live-label">Live</span>
        </div>
      </div>
    </div>
  );
}
