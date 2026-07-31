// UI constants (langflow keeps these in src/constants/constants.ts).

export const CONTAINER_W = 340;
export const CONTAINER_H = 210;

export const CATEGORY_LABELS: Record<string, string> = {
  io: 'Input & Output',
  structural: 'Flow Control',
  agent: 'Agents',
  data: 'Data',
  process: 'Processing',
  evaluation: 'Evaluation',
  files: 'Files',
  knowledge: 'Knowledge',
  tool: 'Tools',
  workflow: 'Workflows',
};
export const CATEGORY_ORDER = [
  'io', 'structural', 'agent',
  'data', 'process', 'evaluation', 'files', 'knowledge',
  'tool', 'workflow',
];

export const REF_PATTERN = /\$\{([A-Za-z][A-Za-z0-9_-]*)/g;
export const DND_MIME = 'application/autogenesis-spec';

export const MAX_HISTORY_SIZE = 100;
export const ALERT_AUTO_DISMISS_MS = 5000;
export const RUN_POLL_INTERVAL_MS = 1000;
