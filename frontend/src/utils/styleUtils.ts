// Node/category colors ported from langflow's utils/styleUtils.ts nodeColors.
// Keys we don't use are kept for parity so future node kinds pick them up.

export const nodeColors: Record<string, string> = {
  inputs: '#10B981',
  outputs: '#AA2411',
  data: '#198BF6',
  prompts: '#4367BF',
  models: '#ab11ab',
  agents: '#903BBE',
  tools: '#06b6d4',
  chains: '#FE7500',
  memories: '#F5B85A',
  str: '#4F46E5',
  Message: '#4f46e5',
  unknown: '#9CA3AF',
};

/** Our palette categories mapped onto langflow's color system. */
export const categoryColors: Record<string, string> = {
  io: nodeColors.inputs,
  structural: nodeColors.data,
  tool: nodeColors.tools,
  agent: nodeColors.agents,
  workflow: nodeColors.prompts,
  data: nodeColors.data,
  process: nodeColors.chains,
  evaluation: nodeColors.outputs,
  files: nodeColors.memories,
  knowledge: nodeColors.models,
};

export function categoryColor(category: string): string {
  return categoryColors[category] ?? nodeColors.unknown;
}
