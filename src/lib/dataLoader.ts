import type { AuditLog, DashboardData, QaPair, ValidationReport, Violation } from '../types';

async function fetchJsonl<T>(path: string): Promise<T[]> {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  const text = await res.text();
  return text
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => JSON.parse(line) as T);
}

async function fetchJson<T>(path: string): Promise<T> {
  const res = await fetch(path, { cache: 'no-store' });
  if (!res.ok) throw new Error(`Failed to fetch ${path}: ${res.status}`);
  return (await res.json()) as T;
}

export async function loadDashboardData(): Promise<DashboardData> {
  const [auditLogs, violations, qaPairs, validationReport] = await Promise.all([
    fetchJsonl<AuditLog>('/data/audit_logs.jsonl'),
    fetchJsonl<Violation>('/data/violations.jsonl'),
    fetchJsonl<QaPair>('/data/qa_pairs.jsonl'),
    fetchJson<ValidationReport>('/data/validation_report.json')
  ]);
  return { auditLogs, violations, qaPairs, validationReport };
}
