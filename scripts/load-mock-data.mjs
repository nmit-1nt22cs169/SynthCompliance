// Copies a mockData/mockData_<n> dataset into public/data/, which the UI
// fetches at runtime. Usage: node scripts/load-mock-data.mjs <1|2|3>
import { copyFileSync, existsSync, mkdirSync, readdirSync, rmSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.join(__dirname, '..');

const set = process.argv[2];
if (!['1', '2', '3'].includes(set)) {
  console.error('Usage: node scripts/load-mock-data.mjs <1|2|3>');
  process.exit(1);
}

const SRC_DIR = path.join(ROOT, 'mockData', `mockData_${set}`);
const OUT_DIR = path.join(ROOT, 'public', 'data');

const files = existsSync(SRC_DIR)
  ? readdirSync(SRC_DIR).filter((f) => f.endsWith('.jsonl') || f.endsWith('.json'))
  : [];

if (files.length === 0) {
  console.error(`No data files found in mockData/mockData_${set}/ — nothing to load.`);
  process.exit(1);
}

rmSync(OUT_DIR, { recursive: true, force: true });
mkdirSync(OUT_DIR, { recursive: true });

for (const file of files) {
  copyFileSync(path.join(SRC_DIR, file), path.join(OUT_DIR, file));
}

console.log(`Loaded mockData_${set} (${files.join(', ')}) into public/data/`);
