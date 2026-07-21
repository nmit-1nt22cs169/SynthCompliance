// Generates the four data-contract files under mockData/mockData_1/.
// Deterministic (seeded RNG) so the dataset is stable across regenerations.
// Run `npm run dev:mock1` afterward to load it into public/data/ for the UI.
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const OUT_DIR = path.join(__dirname, '..', 'mockData', 'mockData_1');

function mulberry32(seed) {
  return function () {
    seed |= 0;
    seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(20260718);
const pick = (arr) => arr[Math.floor(rng() * arr.length)];
const int = (min, max) => Math.floor(rng() * (max - min + 1)) + min;

// ---------- Audit logs ----------
const USERS = [
  { user_id: 'u_2291', role: 'support_agent' },
  { user_id: 'u_1047', role: 'finance_analyst' },
  { user_id: 'u_3390', role: 'contractor' },
  { user_id: 'u_5502', role: 'privacy_officer' },
  { user_id: 'u_4410', role: 'engineer' },
  { user_id: 'u_6650', role: 'hr_specialist' },
  { user_id: 'u_7781', role: 'sales_rep' },
  { user_id: 'u_8802', role: 'admin' },
  { user_id: 'u_9013', role: 'support_agent' },
  { user_id: 'u_1289', role: 'finance_analyst' }
];
const SYSTEMS_BY_ROLE = {
  support_agent: ['crm-core'],
  finance_analyst: ['ledger-svc'],
  contractor: ['iam-core', 'deploy-pipeline'],
  privacy_officer: ['privacy-hub'],
  engineer: ['deploy-pipeline', 'iam-core'],
  hr_specialist: ['hr-core'],
  sales_rep: ['crm-core'],
  admin: ['iam-core', 'ledger-svc', 'crm-core']
};
const RESOURCE_TEMPLATES = {
  'crm-core': ['customer_pii/records/#####', 'customer_pii/exports/#####', 'support/tickets/#####'],
  'ledger-svc': ['finance/ledger/q2_close', 'finance/ledger/q3_accrual', 'finance/invoices/#####'],
  'iam-core': ['iam/roles/admin_grants', 'iam/users/#####/permissions', 'iam/policies/access_review'],
  'privacy-hub': ['dsar/requests/#####', 'privacy/consent_records/#####'],
  'deploy-pipeline': ['deploy/config/prod_gateway', 'deploy/config/billing_worker', 'deploy/releases/#####'],
  'hr-core': ['hr/employee_records/#####', 'hr/employee_exports/2026Q3', 'hr/payroll/#####']
};
const ACTIONS = ['READ', 'UPDATE', 'DELETE', 'EXPORT', 'APPROVE', 'CREATE'];
const SENSITIVITY = ['low', 'medium', 'high', 'critical'];

function resourceFor(system) {
  const tmpl = pick(RESOURCE_TEMPLATES[system]);
  return tmpl.replace('#####', String(int(10000, 99999)));
}

function baseLogRecord(idNum, tsOffsetSec) {
  const u = pick(USERS);
  const system = pick(SYSTEMS_BY_ROLE[u.role]);
  const ts = new Date(Date.UTC(2026, 6, 18, 9, 0, 0) - 3 * 86400000 + tsOffsetSec * 1000);
  return {
    log_id: `log_${idNum}`,
    timestamp: ts.toISOString().replace(/\.\d+Z$/, 'Z'),
    user_id: u.user_id,
    action: pick(ACTIONS),
    resource: resourceFor(system),
    outcome: rng() < 0.92 ? 'success' : 'denied',
    role: u.role,
    sensitivity: pick(SENSITIVITY),
    system
  };
}

// IDs that other files must reference must exist in this set.
const REQUIRED_IDS = [9401, 9508, 9622, 9701, 9744, 9130, 9040, 9214, 9256, 9310, 9931, 9955, 9977, 9988, 9992];
const idPool = new Set(REQUIRED_IDS);
while (idPool.size < 500) idPool.add(int(9000, 9999));
const ids = Array.from(idPool).sort((a, b) => a - b);

const auditLogs = ids.map((idNum, i) => baseLogRecord(idNum, i * 47 + int(0, 20)));
const byId = Object.fromEntries(auditLogs.map((r) => [r.log_id, r]));

// --- seed / narrative records referenced by violations & the validation report ---
Object.assign(byId['log_9931'], {
  timestamp: '2026-07-18T09:26:07Z', user_id: 'u_1047', action: 'APPROVE',
  resource: 'finance/ledger/q2_close', outcome: 'success', role: 'finance_analyst',
  sensitivity: 'high', system: 'ledger-svc'
});
Object.assign(byId['log_9955'], {
  timestamp: '2026-07-18T09:21:33Z', user_id: 'u_3390', action: 'UPDATE',
  resource: 'iam/roles/admin_grants', outcome: 'denied', role: 'contractor',
  sensitivity: 'critical', system: 'iam-core'
});
Object.assign(byId['log_9977'], {
  timestamp: '2026-07-18T09:33:19Z', user_id: 'u_5502', action: 'DELETE',
  resource: 'dsar/requests/6612', outcome: 'success', role: 'privacy_officer',
  sensitivity: 'critical', system: 'privacy-hub'
});
Object.assign(byId['log_9988'], {
  timestamp: '2026-07-18T10:02:41Z', user_id: 'u_4410', action: 'UPDATE',
  resource: 'deploy/config/prod_gateway', outcome: 'success', role: 'engineer',
  sensitivity: 'high', system: 'deploy-pipeline'
});
Object.assign(byId['log_9992'], {
  timestamp: '2026-07-18T09:40:02Z', user_id: 'u_2291', action: 'READ',
  resource: 'customer_pii/records/88213', outcome: 'success', role: 'support_agent',
  sensitivity: 'high', system: 'crm-core'
});
// schema-validity anomalies (deliberately malformed, matching the flagged issues)
Object.assign(byId['log_9401'], { sensitivity: '' });
Object.assign(byId['log_9508'], { timestamp: '07/18/2026 09:15am' });
Object.assign(byId['log_9622'], { action: 'XPORT_UNK' });
// pii-leakage anomalies (raw entity leaked into the resource path)
Object.assign(byId['log_9701'], { resource: 'support/tickets/44210/contact/jsmith@examplecorp.com' });
Object.assign(byId['log_9744'], { resource: 'hr/employee_exports/2026Q3/ssn/512-34-4471' });
// duplicate-check cluster: 9040 is the original, 9130/9214/9256/9310 are near-duplicates
Object.assign(byId['log_9040'], {
  timestamp: '2026-07-18T08:58:12Z', user_id: 'u_9013', action: 'READ',
  resource: 'customer_pii/records/50210', outcome: 'success', role: 'support_agent',
  sensitivity: 'high', system: 'crm-core'
});
Object.assign(byId['log_9130'], { ...byId['log_9040'], log_id: 'log_9130', timestamp: '2026-07-18T08:58:14Z' });
Object.assign(byId['log_9214'], { ...byId['log_9040'], log_id: 'log_9214', timestamp: '2026-07-18T08:58:19Z' });
Object.assign(byId['log_9256'], { ...byId['log_9040'], log_id: 'log_9256', timestamp: '2026-07-18T08:58:23Z' });
Object.assign(byId['log_9310'], { ...byId['log_9040'], log_id: 'log_9310', timestamp: '2026-07-18T08:58:30Z' });

auditLogs.sort((a, b) => (a.timestamp < b.timestamp ? -1 : 1));

// ---------- Violations ----------
const VIOLATION_DEFS = [
  { type: 'segregation_of_duties', controls: ['SOD-04', 'SOD-05'] },
  { type: 'unauthorized_access', controls: ['AC-11', 'AC-12'] },
  { type: 'late_dsar', controls: ['PRIV-02', 'PRIV-03'] },
  { type: 'missing_approval', controls: ['CHG-07', 'CHG-08'] }
];
const SEVERITIES = ['critical', 'high', 'high', 'medium', 'medium', 'low'];

function explanationFor(type, log) {
  switch (type) {
    case 'segregation_of_duties':
      return `User ${log.user_id} both created and approved the change to ${log.resource}, violating maker-checker separation.`;
    case 'unauthorized_access':
      return `${log.role.replace('_', ' ')} account ${log.user_id} accessed ${log.resource} outside an authorized change or ticket window.`;
    case 'late_dsar':
      return `DSAR request ${log.resource} was fulfilled after the 30-day regulatory window had elapsed.`;
    case 'missing_approval':
      return `Change to ${log.resource} was deployed by ${log.user_id} without a recorded approval step in the change log.`;
    default:
      return `Anomaly detected on ${log.resource} performed by ${log.user_id}.`;
  }
}

const violationCount = 147;
// violation_ids that must exist with specific content (seeds) or must exist for label_alignment flags
const SEED_VIOLATIONS = [
  { violation_id: 'V-1042', log_id: 'log_9931', violation_type: 'segregation_of_duties', control_id: 'SOD-04', severity: 'high', explanation: 'Same user both created and approved the ledger close entry, violating maker-checker separation.' },
  { violation_id: 'V-1043', log_id: 'log_9955', violation_type: 'unauthorized_access', control_id: 'AC-11', severity: 'critical', explanation: 'Contractor account attempted to modify admin role grants without an active change ticket.' },
  { violation_id: 'V-1044', log_id: 'log_9977', violation_type: 'late_dsar', control_id: 'PRIV-02', severity: 'medium', explanation: 'DSAR deletion request fulfilled 34 days after intake, exceeding the 30-day regulatory window.' },
  { violation_id: 'V-1045', log_id: 'log_9988', violation_type: 'missing_approval', control_id: 'CHG-07', severity: 'high', explanation: 'Production config change deployed without a recorded approval step in the change log.' },
  { violation_id: 'V-1046', log_id: 'log_9992', violation_type: 'unauthorized_access', control_id: 'AC-11', severity: 'medium', explanation: 'Support agent re-accessed a closed customer PII record outside an active ticket window.' }
];
const LABEL_ALIGNMENT_FLAGGED_IDS = ['V-1029', 'V-1037', 'V-1005', 'V-1061', 'V-1088', 'V-1103'];
const LABEL_ISSUES = {
  'V-1029': 'control_id does not match violation_type taxonomy',
  'V-1037': 'severity inconsistent with explanation text',
  'V-1005': 'control_id does not match violation_type taxonomy',
  'V-1061': 'control_id used across two different violation_type categories',
  'V-1088': 'severity inconsistent with explanation text',
  'V-1103': 'violation_type not present in control taxonomy'
};

const violationNums = new Set([42, 43, 44, 45, 46]);
LABEL_ALIGNMENT_FLAGGED_IDS.forEach((id) => violationNums.add(Number(id.split('-')[1]) - 1000));
while (violationNums.size < violationCount) violationNums.add(int(1, 1147));
const sortedNums = Array.from(violationNums).sort((a, b) => a - b).slice(0, violationCount);

const seedByNum = Object.fromEntries(SEED_VIOLATIONS.map((v) => [Number(v.violation_id.split('-')[1]) - 1000, v]));
const auditPool = auditLogs.filter((l) => typeof l.timestamp === 'string' && l.timestamp.includes('T'));

const violations = sortedNums.map((num) => {
  const violation_id = `V-${1000 + num}`;
  if (seedByNum[num]) return seedByNum[num];
  const def = pick(VIOLATION_DEFS);
  const log = pick(auditPool);
  return {
    violation_id,
    log_id: log.log_id,
    violation_type: def.type,
    control_id: pick(def.controls),
    severity: pick(SEVERITIES),
    explanation: explanationFor(def.type, log)
  };
});

// ---------- QA pairs ----------
const SEED_QA = [
  { qa_id: 'QA-201', question: 'Was the Q2 ledger close reviewed by someone other than the preparer?', answer: 'No — the same user (u_1047) both created and approved the entry, a segregation-of-duties violation.', evidence_log_ids: ['log_9931'], grounding: 'high' },
  { qa_id: 'QA-202', question: 'Did any contractor accounts attempt privileged IAM changes?', answer: 'Yes — contractor u_3390 attempted to modify admin role grants; the action was denied by policy.', evidence_log_ids: ['log_9955'], grounding: 'high' },
  { qa_id: 'QA-203', question: 'Were all DSAR deletion requests completed within 30 days?', answer: 'No — one deletion request (dsar/requests/6612) was fulfilled after 34 days.', evidence_log_ids: ['log_9977'], grounding: 'medium' }
];
const QA_TEMPLATES = [
  (v, l) => ({
    question: `Was there any unauthorized access involving ${l.resource}?`,
    answer: `Yes — ${l.user_id} (${l.role.replace('_', ' ')}) accessed ${l.resource}, flagged under control ${v.control_id}.`,
    grounding: 'high'
  }),
  (v, l) => ({
    question: `Is the change to ${l.resource} properly approved?`,
    answer: `No — no approval record was found for the change made by ${l.user_id}, violating control ${v.control_id}.`,
    grounding: 'medium'
  }),
  (v, l) => ({
    question: `Did ${l.user_id} perform both the creation and approval of ${l.resource}?`,
    answer: `Yes — this is a segregation-of-duties violation under control ${v.control_id}.`,
    grounding: 'high'
  })
];

const qaCount = 100;
const qaPairs = [...SEED_QA];
let qaNum = 204;
while (qaPairs.length < qaCount) {
  const idx = int(0, violations.length - 1);
  const v = violations[idx];
  const log = byId[v.log_id] || pick(auditPool);
  const tmpl = pick(QA_TEMPLATES);
  const { question, answer, grounding } = tmpl(v, log);
  qaPairs.push({
    qa_id: `QA-${qaNum++}`,
    question,
    answer,
    evidence_log_ids: [log.log_id],
    grounding
  });
}

// ---------- Validation report ----------
const validationReport = {
  run_id: 'run_2026_07_18_0431',
  generated_at: '2026-07-18T09:45:11Z',
  dataset_targets: { audit_logs: 500, violations: 150, qa_pairs: 100, investigation_summaries: 2 },
  dataset_actual: { audit_logs: auditLogs.length, violations: violations.length, qa_pairs: qaPairs.length, investigation_summaries: 2 },
  validators: {
    schema_validity: {
      target_pass_rate: 0.98, actual_pass_rate: 0.994, rows_checked: 500, rows_failed: 3, status: 'pass',
      flagged: [
        { log_id: 'log_9401', field: 'sensitivity', issue: 'missing enum value' },
        { log_id: 'log_9508', field: 'timestamp', issue: 'non-ISO8601 format' },
        { log_id: 'log_9622', field: 'action', issue: 'unrecognized action code' }
      ]
    },
    pii_leakage: {
      target_detections: 0, actual_detections: 2, rows_checked: 500, status: 'warn',
      flagged: [
        { log_id: 'log_9701', entity: 'EMAIL', value_redacted: 'j***@●●●●.com' },
        { log_id: 'log_9744', entity: 'SSN', value_redacted: '●●●-●●-4471' }
      ]
    },
    duplicate_check: {
      target_max_rate: 0.02, actual_rate: 0.008, rows_checked: 500, rows_flagged: 4, status: 'pass',
      flagged: [
        { log_id: 'log_9130', duplicate_of: 'log_9040', similarity: 0.97 },
        { log_id: 'log_9214', duplicate_of: 'log_9040', similarity: 0.94 },
        { log_id: 'log_9256', duplicate_of: 'log_9040', similarity: 0.95 },
        { log_id: 'log_9310', duplicate_of: 'log_9040', similarity: 0.93 }
      ]
    },
    label_alignment: {
      target_pass_rate: 0.95, actual_pass_rate: 0.961, rows_checked: violations.length, rows_failed: 6, status: 'pass',
      flagged: LABEL_ALIGNMENT_FLAGGED_IDS.map((violation_id) => ({ violation_id, issue: LABEL_ISSUES[violation_id] }))
    },
    scenario_coverage: { normal: 302, suspicious: 71, violation: 104, false_positive: 23 }
  },
  pipeline_stages: [
    { stage: 'Policy Templates', status: 'completed', duration_ms: 1840 },
    { stage: 'Event Generator', status: 'completed', duration_ms: 22110 },
    { stage: 'Scenario Composer', status: 'completed', duration_ms: 15430 },
    { stage: 'Regulation Annotator', status: 'completed', duration_ms: 9870 },
    { stage: 'NeMo Curator', status: 'completed', duration_ms: 31220 },
    { stage: 'Output Datasets', status: 'completed', duration_ms: 640 }
  ]
};

// ---------- Write files ----------
const jsonl = (rows) => rows.map((r) => JSON.stringify(r)).join('\n') + '\n';
writeFileSync(path.join(OUT_DIR, 'audit_logs.jsonl'), jsonl(auditLogs));
writeFileSync(path.join(OUT_DIR, 'violations.jsonl'), jsonl(violations));
writeFileSync(path.join(OUT_DIR, 'qa_pairs.jsonl'), jsonl(qaPairs));
writeFileSync(path.join(OUT_DIR, 'validation_report.json'), JSON.stringify(validationReport, null, 2) + '\n');

console.log(`audit_logs: ${auditLogs.length}, violations: ${violations.length}, qa_pairs: ${qaPairs.length}`);
