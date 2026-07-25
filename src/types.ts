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

export interface GoldenSetFidelity {
  label_fidelity_score: number;
  statistical_fidelity_score: number;
  matched_seeds?: number;
  total_seeds?: number;
  classes_matched?: number;
  classes_total?: number;
  max_field_deviation_pct?: number;
  status: ValidatorStatus | string;
  notes?: string;
}

export interface ConfusionMatrix {
  tp: number;
  fp: number;
  tn: number;
  fn: number;
}

export interface RetrainMetrics {
  precision: number;
  recall: number;
  f1: number;
  accuracy: number;
}

export interface RetrainHistoryEntry {
  model_version: number;
  trained_at: string;
  cumulative_train_size: number;
  metrics_after: RetrainMetrics;
}

export interface TstrMetrics {
  baseline_rare_recall: number;
  synthetic_trained_rare_recall: number;
  recall_lift: number;
  train_size?: number;
  eval_size?: number;
  eval_violation_rate?: number;
  train_violation_rate?: number;
  status?: string;
  model?: string;
  notes?: string;
  // Persisted-model retraining (RETRAIN_MODEL=true, only fires when recall regressed/didn't
  // improve vs. the previous run — see feedback_loop.improved). Absent/false when disabled
  // or not triggered this run. `retrain_enabled` distinguishes "feature off" from "feature on,
  // not triggered this run" — always set, unlike `retrained` which only means "fired this run."
  retrain_enabled?: boolean;
  retrained?: boolean;
  model_version?: number;
  cumulative_train_size?: number;
  trained_at?: string;
  post_retrain_recall?: number;
  // Rolling history of past retrain snapshots, oldest first — populated even on runs that
  // didn't retrain this time, so a trend chart isn't limited to retrain-triggering runs only.
  retrain_history?: RetrainHistoryEntry[];
  // Before = the previous persisted checkpoint (if any) evaluated on this run's eval set;
  // null on the very first retrain, since there's no prior checkpoint to compare against.
  confusion_matrix_before?: ConfusionMatrix | null;
  confusion_matrix_after?: ConfusionMatrix;
  metrics_before?: RetrainMetrics | null;
  metrics_after?: RetrainMetrics;
  // Transformer scorers (offline cluster-trained via scripts/train_transformers.py,
  // leakage-safe SOX-train / GDPR-eval pack split). Absent if no checkpoint run.
  transformer_models?: TransformerModelMetrics[];
  transformer_best_model?: string;
  distilbert_rare_recall?: number;
  distilbert_recall_lift_vs_rule?: number;
  distilbert_recall_lift_vs_lr?: number;
  deberta_rare_recall?: number;
  deberta_recall_lift_vs_rule?: number;
  deberta_recall_lift_vs_lr?: number;
  lr_strict_rare_recall?: number;
  rule_strict_rare_recall?: number;
}

export interface TransformerModelMetrics {
  transformer_model: string;
  transformer_rare_recall: number;
  transformer_recall_lift_vs_rule: number;
  transformer_recall_lift_vs_lr: number | null;
  transformer_status?: string;
  transformer_train_size?: number;
  transformer_eval_size?: number;
  transformer_eval_violation_rate?: number;
  transformer_train_pack?: string;
  transformer_eval_pack?: string;
  transformer_device?: string;
  transformer_mode?: string;
  lr_strict_rare_recall?: number;
  rule_strict_rare_recall?: number;
}

export interface ValidationReport {
  run_id: string;
  generated_at: string;
  dataset_targets: {
    audit_logs: number;
    violations: number;
    qa_pairs: number;
    llm_fields: number;
  };
  dataset_actual: {
    audit_logs: number;
    violations: number;
    qa_pairs: number;
    llm_fields: number;
  };
  validators: {
    schema_validity: SchemaValidityValidator;
    pii_leakage: PiiLeakageValidator;
    duplicate_check: DuplicateCheckValidator;
    label_alignment: LabelAlignmentValidator;
    scenario_coverage: ScenarioCoverage;
  };
  golden_set_fidelity?: GoldenSetFidelity;
  tstr_metrics?: TstrMetrics;
  repair_log?: { repaired_log_ids: string[]; iterations: number };
  feedback_loop?: {
    new_violation_patterns: string[];
    next_violation_type_weights: Record<string, number>;
    improved: boolean;
  };
  pipeline_stages: PipelineStage[];
}

export interface DashboardData {
  auditLogs: AuditLog[];
  violations: Violation[];
  qaPairs: QaPair[];
  validationReport: ValidationReport;
}

export type TabId = 'overview' | 'pipeline' | 'validation' | 'data' | 'copilot' | 'proof';

export type DataTable = 'auditLogs' | 'violations' | 'qaPairs';

export interface JobConfig {
  packs: string[];
  control_classes: string[];
  scenario_mix: {
    normal: number;
    suspicious: number;
    violation: number;
    false_positive: number;
  };
  n_logs: number;
  industry: string;
}
