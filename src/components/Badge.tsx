interface BadgeProps {
  status: string;
}

export function Badge({ status }: BadgeProps) {
  return <span className={`badge badge-${status}`}>{status}</span>;
}

interface SeverityBadgeProps {
  severity: string;
}

export function SeverityBadge({ severity }: SeverityBadgeProps) {
  const known = ['critical', 'high', 'medium', 'low'].includes(severity) ? severity : 'medium';
  return <span className={`severity-badge severity-${known}`}>{severity}</span>;
}
