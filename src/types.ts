export type Outcome = 'success' | 'denied';
export type Sensitivity = 'low' | 'medium' | 'high' | 'critical' | string;

export interface AuditLog {
  log_id: string;
  timestamp: string;
  user_id: string;
  action: string;
  resource: string;
  outcome: Outcome;
  role: string;
  sensitivity: Sensitivity;
  system: string;
}

export type Severity = 'critical' | 'high' | 'medium' | 'low';

export interface Violation {
  violation_id: string;
  log_id: string;
  violation_type: string;
  control_id: string;
  severity: Severity;
  explanation: string;
}

export interface QaPair {
  qa_id: string;
  question: string;
  answer: string;
  evidence_log_ids: string[];
  grounding: 'high' | 'medium' | 'low' | string;
}

export type ValidatorStatus = 'pass' | 'warn' | 'fail';

export interface SchemaValidityValidator {
  target_pass_rate: number;
  actual_pass_rate: number;
  rows_checked: number;
  rows_failed: number;
  status: ValidatorStatus;
  flagged: { log_id: string; field: string; issue: string }[];
}

export interface PiiLeakageValidator {
  target_detections: number;
  actual_detections: number;
  rows_checked: number;
  status: ValidatorStatus;
  flagged: { log_id: string; entity: string; value_redacted: string }[];
}

export interface DuplicateCheckValidator {
  target_max_rate: number;
  actual_rate: number;
  rows_checked: number;
  rows_flagged: number;
  status: ValidatorStatus;
  flagged: { log_id: string; duplicate_of: string; similarity: number }[];
}

export interface LabelAlignmentValidator {
  target_pass_rate: number;
  actual_pass_rate: number;
  rows_checked: number;
  rows_failed: number;
  status: ValidatorStatus;
  flagged: { violation_id: string; issue: string }[];
}

export interface ScenarioCoverage {
  normal: number;
  suspicious: number;
  violation: number;
  false_positive: number;
}

export interface PipelineStage {
  stage: string;
  status: 'completed' | 'running' | 'failed' | 'skipped';
  duration_ms: number;
}

export interface ValidationReport {
  run_id: string;
  generated_at: string;
  dataset_targets: {
    audit_logs: number;
    violations: number;
    qa_pairs: number;
    investigation_summaries: number;
  };
  dataset_actual: {
    audit_logs: number;
    violations: number;
    qa_pairs: number;
    investigation_summaries: number;
  };
  validators: {
    schema_validity: SchemaValidityValidator;
    pii_leakage: PiiLeakageValidator;
    duplicate_check: DuplicateCheckValidator;
    label_alignment: LabelAlignmentValidator;
    scenario_coverage: ScenarioCoverage;
  };
  pipeline_stages: PipelineStage[];
}

export interface DashboardData {
  auditLogs: AuditLog[];
  violations: Violation[];
  qaPairs: QaPair[];
  validationReport: ValidationReport;
}

export type TabId = 'overview' | 'pipeline' | 'validation' | 'data' | 'copilot';
