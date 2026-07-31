import type { Node } from '@xyflow/react';

import type { GatewayResponse } from '../controllers/gateway';

// ---------------------------------------------------------------------------
// Wire contracts (mirror autogenesis/canvas/types.py)
// ---------------------------------------------------------------------------

export interface ParamSpec {
  name: string;
  label: string;
  type: 'string' | 'number' | 'boolean' | 'select' | 'json';
  required: boolean;
  default: unknown;
  options?: string[] | null;
  multiline: boolean;
  description: string;
  connectable: boolean;
}

export type PortType = 'text' | 'list' | 'object' | 'any';
export interface PortSpec { name: string; label: string; type: PortType; description?: string; }

/** Data-flow port colors (a small closed set; Langflow-style colored handles). */
export const PORT_COLORS: Record<PortType, string> = {
  text: '#4F46E5',   // indigo
  list: '#D97706',   // amber
  object: '#059669', // emerald
  any: '#94A3B8',    // slate
};

export function portsCompatible(source: PortType, target: PortType): boolean {
  return source === target || source === 'any' || target === 'any';
}

export interface NodeSpec {
  id: string;
  // Palette group: io / structural / agent / workflow, or a capability's
  // canvas category (data / process / evaluation / files / knowledge / tool).
  category: string;
  step_type?: string | null;
  target?: string | null;
  label: string;
  description: string;
  icon?: string;
  params: ParamSpec[];
  has_task: boolean;
  has_items: boolean;
  container: boolean;
  inputs?: PortSpec[];
  outputs?: PortSpec[];
  mount_types?: string[];
  // Plugin grouping (category === 'plugin'): the palette nests this node under
  // a collapsible sub-group for its plugin.
  plugin?: string;
  plugin_label?: string;
}

export interface MountItem { name: string; description: string; }
export type MountRosters = Record<string, MountItem[]>;
export const MOUNT_LABELS: Record<string, string> = {
  tools: 'Tools', skills: 'Skills', connectors: 'Connectors', agents: 'Agents',
  environments: 'Environments', workflows: 'Workflows (Tool Mode)',
};

export interface FlowSummary { id: string; name: string; description: string; version: string; published: boolean; updated_at?: string | null; node_count: number; }
export interface FlowStatus { name: string; in_library: boolean; }

export interface GraphNodeDoc {
  id: string;
  type: 'step' | 'input' | 'output';
  step_type?: string | null;
  target?: string | null;
  task?: string;
  args?: Record<string, unknown>;
  items?: string;
  attrs?: Record<string, unknown>;
  mounts?: Record<string, string[]>;
  name?: string;
  input_type?: string;
  required?: boolean;
  default?: unknown;
  description?: string;
  value?: string;
  parent?: string | null;
  slot?: 'body' | 'then' | 'else';
  frozen?: boolean;
  frozen_output?: unknown;
  position: { x: number; y: number };
}

export interface GraphEdgeDoc { id: string; source: string; target: string; param: string; source_port?: string; }

// Sticky-note annotation — visual only, stored alongside (not inside) the graph.
export interface NoteDoc { id: string; position: { x: number; y: number }; width: number; height: number; text: string; color: string; }

export interface FlowGraphDoc {
  id: string;
  name: string;
  description: string;
  version: string;
  document_version: number;
  nodes: GraphNodeDoc[];
  edges: GraphEdgeDoc[];
  notes?: NoteDoc[];
  published: boolean;
  program_hash: string;
}

export type RequestFn = (method: string, params?: Record<string, unknown>) => Promise<GatewayResponse>;
export type FrameState = 'pending' | 'ready' | 'running' | 'retry_wait' | 'cached' | 'succeeded' | 'failed' | 'cancelled' | 'skipped';

export interface FrameDoc { key: string; step_id: string; state: FrameState; item_index?: number | null; iteration?: number | null; output?: unknown; error?: string | null; started_at?: string | null; finished_at?: string | null; }
export interface InvocationDoc { key: string; frame_key: string; capability_type: string; capability_name: string; state: string; input: Record<string, unknown>; attempts: Array<{ number: number; state: string; error?: string | null }>; output?: unknown; error?: string | null; cached: boolean; token_cost: number; started_at?: string | null; finished_at?: string | null; }
export interface RunData { state: string; frames: Record<string, FrameDoc>; invocations: Record<string, InvocationDoc>; }

// ---------------------------------------------------------------------------
// React Flow node data
// ---------------------------------------------------------------------------

// Sticky-note node payload (Langflow NoteNode): editable text + a color key.
export type NoteColor = 'amber' | 'neutral' | 'rose' | 'blue' | 'lime';
export interface NoteData { text: string; color: NoteColor; }

export interface CanvasData extends Record<string, unknown> {
  spec?: NodeSpec;
  type: 'step' | 'input' | 'output';
  // Present only on sticky-note nodes (type 'noteNode'); excluded from the graph.
  note?: NoteData;
  // Editable display name (Langflow display_name). Distinct from the node id
  // that `${id}` references bind to; falls back to the spec label when unset.
  name?: string;
  stepType?: string;
  target?: string;
  task: string;
  args: Record<string, string>;
  items: string;
  attrs: Record<string, string>;
  io: { name: string; input_type: string; required: boolean; default: string; description: string; value: string };
  // Agent capability mounts, keyed by type (tools/skills/connectors/...).
  mounts: Record<string, string[]>;
  runState?: FrameState;
  runCount?: number;
  minimized?: boolean;
  frozen?: boolean;
  frozenOutput?: unknown;
  boundParams: Set<string>;
  update: (nodeId: string, patch: Partial<CanvasData> | ((data: CanvasData) => Partial<CanvasData>)) => void;
}

export type CanvasNode = Node<CanvasData>;

// ---------------------------------------------------------------------------
// Shared constants & helpers
// ---------------------------------------------------------------------------

export { CATEGORY_LABELS, CATEGORY_ORDER, CONTAINER_H, CONTAINER_W, DND_MIME, REF_PATTERN } from '../constants/constants';

let placedCounter = 0;
export function nextPlacement(): number { placedCounter += 1; return placedCounter; }
export function freshId(): string { return `n${Date.now().toString(36)}${nextPlacement()}`; }

export function specKeyFor(doc: GraphNodeDoc): string {
  if (doc.type !== 'step') return `io/${doc.type}`;
  return ['tool', 'agent', 'workflow'].includes(doc.step_type ?? '')
    ? `${doc.step_type}/${doc.target ?? ''}`
    : `step/${doc.step_type}`;
}
