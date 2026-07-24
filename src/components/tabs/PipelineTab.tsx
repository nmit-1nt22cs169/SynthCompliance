import { useEffect, useMemo, useState } from 'react';
import { Badge } from '../Badge';
import { deriveLineChart } from '../../lib/derive';
import { fetchTaxonomy, startJob, subscribeJobEvents, type JobEvent } from '../../lib/api';
import type { JobConfig, ValidationReport } from '../../types';

const INDUSTRIES = [
  { id: 'financial_services', label: 'Financial Services' },
  { id: 'healthcare', label: 'Healthcare' },
  { id: 'retail', label: 'Retail / E-commerce' },
  { id: 'technology', label: 'Technology / SaaS' }
];

const DEFAULT_MIX = { normal: 60, suspicious: 15, violation: 20, false_positive: 5 };

interface PipelineTabProps {
  report: ValidationReport | null;
  accent: string;
  onJobActiveChange?: (active: boolean) => void;
  onJobComplete?: () => void;
}

export function PipelineTab({ report, accent, onJobActiveChange, onJobComplete }: PipelineTabProps) {
  const [packs, setPacks] = useState<string[]>(['SOX', 'GDPR']);
  const [controlClasses, setControlClasses] = useState<string[]>([
    'segregation_of_duties',
    'late_dsar',
    'access_lifecycle_breach'
  ]);
  const [mix, setMix] = useState(DEFAULT_MIX);
  const [nLogs, setNLogs] = useState(500);
  const [industry, setIndustry] = useState('financial_services');
  const [taxonomyClasses, setTaxonomyClasses] = useState<{ id: string; label: string; pack: string }[]>([]);
  const [taxonomyLoading, setTaxonomyLoading] = useState(true);
  const [taxonomyError, setTaxonomyError] = useState<string | null>(null);
  const [jobEvents, setJobEvents] = useState<JobEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTaxonomyLoading(true);
    fetchTaxonomy()
      .then((t) => {
        const classes = Object.entries(t.taxonomy).map(([id, meta]) => ({
          id,
          label: meta.label,
          pack: meta.pack
        }));
        setTaxonomyClasses(classes);
        setTaxonomyError(null);
      })
      .catch((e) => {
        setTaxonomyError(e instanceof Error ? e.message : 'API unavailable — start npm run dev:api');
        setTaxonomyClasses([]);
      })
      .finally(() => setTaxonomyLoading(false));
  }, []);

  const mixTotal = mix.normal + mix.suspicious + mix.violation + mix.false_positive;
  const mixValid = mixTotal === 100;

  const filteredClasses = useMemo(
    () => taxonomyClasses.filter((c) => packs.includes(c.pack)),
    [taxonomyClasses, packs]
  );

  const togglePack = (pack: string) => {
    setPacks((prev) => (prev.includes(pack) ? prev.filter((p) => p !== pack) : [...prev, pack]));
  };

  const updateMix = (key: keyof typeof mix, value: number) => {
    setMix((prev) => ({ ...prev, [key]: Math.max(0, Math.min(100, value)) }));
  };

  const runPipeline = async () => {
    setError(null);
    setRunning(true);
    onJobActiveChange?.(true);
    setJobEvents([]);
    const config: JobConfig = {
      packs,
      control_classes: controlClasses,
      scenario_mix: {
        normal: mix.normal / 100,
        suspicious: mix.suspicious / 100,
        violation: mix.violation / 100,
        false_positive: mix.false_positive / 100
      },
      n_logs: nLogs,
      industry
    };
    try {
      const { job_id } = await startJob(config);
      subscribeJobEvents(
        job_id,
        (ev) => setJobEvents((prev) => [...prev, ev]),
        () => {
          setRunning(false);
          onJobActiveChange?.(false);
          onJobComplete?.();
        }
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
      onJobActiveChange?.(false);
    }
  };

  const lineChart = report ? deriveLineChart(report) : null;
  const latest = jobEvents[jobEvents.length - 1];

  return (
    <div>
      <div className="glass-panel tab-panel wizard-panel">
        <div className="panel-title">Pipeline Wizard</div>
        <div className="wizard-grid">
          <div className="wizard-field">
            <label className="wizard-label">Regulation Packs</label>
            <div className="chip-row">
              {['SOX', 'GDPR'].map((p) => (
                <button
                  key={p}
                  type="button"
                  className={`chip${packs.includes(p) ? ' active' : ''}`}
                  onClick={() => togglePack(p)}
                >
                  {p}
                </button>
              ))}
            </div>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="control-classes">
              Control Classes
            </label>
            <select
              id="control-classes"
              multiple
              className="wizard-select"
              size={6}
              value={controlClasses}
              disabled={taxonomyLoading || !!taxonomyError}
              onChange={(e) => {
                const selected = Array.from(e.target.selectedOptions, (o) => o.value);
                setControlClasses(selected);
              }}
            >
              {taxonomyLoading && <option disabled>Loading taxonomy from API…</option>}
              {taxonomyError && <option disabled>{taxonomyError}</option>}
              {!taxonomyLoading &&
                !taxonomyError &&
                filteredClasses.map((c) => (
                  <option key={c.id} value={c.id}>
                    [{c.pack}] {c.label}
                  </option>
                ))}
            </select>
            <div className="wizard-hint">Hold Ctrl/Cmd to select multiple. Default demo: SoD + Late DSAR + Access Lifecycle.</div>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="industry">
              Industry Profile
            </label>
            <select
              id="industry"
              className="wizard-select single"
              value={industry}
              onChange={(e) => setIndustry(e.target.value)}
            >
              {INDUSTRIES.map((i) => (
                <option key={i.id} value={i.id}>
                  {i.label}
                </option>
              ))}
            </select>
          </div>

          <div className="wizard-field">
            <label className="wizard-label" htmlFor="n-logs">
              Dataset Size (audit logs)
            </label>
            <input
              id="n-logs"
              type="number"
              min={50}
              max={2000}
              step={50}
              className="wizard-input"
              value={nLogs}
              onChange={(e) => setNLogs(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="wizard-field" style={{ marginTop: 16 }}>
          <label className="wizard-label">Scenario Mix (must sum to 100%)</label>
          <div className="slider-grid">
            {(['normal', 'suspicious', 'violation', 'false_positive'] as const).map((key) => (
              <div key={key} className="slider-row">
                <span className="slider-name">{key.replace('_', ' ')}</span>
                <input
                  type="range"
                  className="slider-input"
                  min={0}
                  max={100}
                  value={mix[key]}
                  onChange={(e) => updateMix(key, Number(e.target.value))}
                />
                <span className="slider-val">{mix[key]}%</span>
              </div>
            ))}
          </div>
          <div className={`mix-total${mixValid ? '' : ' invalid'}`}>Total: {mixTotal}%</div>
        </div>

        <div className="wizard-actions">
          <button type="button" className="copilot-button" disabled={running || !mixValid || packs.length === 0} onClick={() => runPipeline()}>
            {running ? 'Running…' : 'Run Pipeline'}
          </button>
        </div>

        {error && <div className="wizard-error">{error}</div>}

        {(running || jobEvents.length > 0) && (
          <div className="job-feed">
            <div className="panel-title" style={{ marginBottom: 10 }}>
              Live Job Stream
            </div>
            {latest && (
              <div className="job-latest">
                <Badge status={latest.stage === 'failed' ? 'fail' : latest.stage === 'complete' ? 'pass' : 'warn'} />
                <span>{latest.message}</span>
                {latest.count != null && latest.total != null && (
                  <span className="job-count">
                    {latest.count} / {latest.total}
                  </span>
                )}
              </div>
            )}
            <div className="job-log">
              {jobEvents.slice(-8).map((ev, i) => (
                <div key={i} className="job-log-line">
                  <span className="job-stage">[{ev.stage}]</span> {ev.message}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {lineChart && report && (
        <>
          <div className="glass-panel tab-panel panel-pad">
            <div className="panel-title">Stage Duration Trend</div>
            <svg viewBox={`0 0 ${lineChart.w} ${lineChart.h}`} style={{ width: '100%', height: 200, overflow: 'visible' }}>
              <path d={lineChart.areaPath} fill={accent} opacity={0.14} />
              <path d={lineChart.linePath} fill="none" stroke={accent} strokeWidth={2.5} />
              {lineChart.points.map((p, i) => (
                <g key={i}>
                  <circle cx={p.x} cy={p.y} r={4} fill={accent} stroke="var(--surface-hole)" strokeWidth={2} />
                  <text x={p.x} y={p.labelY} fontSize={11} fill="var(--text-tertiary)" textAnchor="middle">
                    {p.durationLabel}
                  </text>
                  <text x={p.x} y={lineChart.axisY} fontSize={11} fill="var(--text-secondary)" textAnchor="middle">
                    {p.shortName}
                  </text>
                </g>
              ))}
            </svg>
          </div>

          <div className="glass-panel panel-pad">
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
            {report.repair_log && report.repair_log.repaired_log_ids.length > 0 && (
              <div className="repair-note">
                Repair loop fixed {report.repair_log.repaired_log_ids.length} row(s) in {report.repair_log.iterations} iteration(s).
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
