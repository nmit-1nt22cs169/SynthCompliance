interface InfoTipProps {
  text: string;
}

export function InfoTip({ text }: InfoTipProps) {
  return (
    <span className="info-tip" tabIndex={0}>
      <span className="info-tip-icon" aria-hidden="true">i</span>
      <span className="info-tip-bubble" role="tooltip">{text}</span>
    </span>
  );
}
