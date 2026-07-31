import { useEffect, useState } from 'react';
import { Handle, NodeResizer, NodeToolbar, Position, type NodeProps } from '@xyflow/react';
import { ChevronDown, ChevronRight, ClipboardCopy, Copy, Download, FileText, Info, Loader2, Maximize2, Minimize2, MoreHorizontal, PencilLine, Play, Save, SlidersHorizontal, Snowflake, TextSearch, Trash2 } from 'lucide-react';

import { MountPicker } from './CapabilityPicker';
import ShadTooltip from '../components/common/shadTooltipComponent';
import { Button } from '../components/ui/button';
import { cn } from '../utils/utils';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator,
  DropdownMenuShortcut, DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';
import { Input } from '../components/ui/input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Switch } from '../components/ui/switch';
import { Textarea } from '../components/ui/textarea';
import { NodeIcon } from '../icons';
import { PORT_COLORS, type CanvasData, type CanvasNode, type NoteColor, type NodeSpec, type ParamSpec, type PortSpec, type PortType } from './types';

function runClass(data: CanvasData): string { return data.runState ? ` run-${data.runState}` : ''; }

// Typed data-flow handles (Langflow-style colored dots): color = port type.
const IO_INPUT_PORT: Record<string, PortType> = { string: 'text', array: 'list', object: 'object', number: 'text', boolean: 'text' };
function portColor(type: PortType): string { return PORT_COLORS[type] ?? PORT_COLORS.any; }
function inputPortType(spec: NodeSpec | undefined, name: string): PortType {
  return spec?.inputs?.find((port) => port.name === name)?.type ?? 'any';
}

// The `--handle-color` var lets the CSS neon-glow (canvas.css) match the dot's
// own datatype color, mirroring Langflow's getNeonShadow(handleColor, …).
function handleStyle(type: PortType, extra?: React.CSSProperties): React.CSSProperties {
  const color = portColor(type);
  return { background: color, ['--handle-color' as string]: color, ...extra };
}

function InHandle({ id, type }: { id: string; type: PortType }) {
  return <Handle type="target" id={id} position={Position.Left} className="lf-handle in" style={handleStyle(type)} title={`${id} · ${type}`} />;
}

/** A single output handle (Langflow-clean, one row). Capability nodes are
 * polymorphic — one adaptive port whose sub-path (message/data/files) is
 * inferred from what you connect it to; other nodes carry their one typed
 * output. ``ioType`` colors the io-input node's output by its declared type. */
// One output row — Langflow NodeOutputfield: an h-11 bg-muted band with the
// output name + (single-output only) an inspect button, then the source handle.
function OutputRow({ nodeId, name, label, type, hint, inspect, frozen, last }: {
  nodeId?: string; name: string; label: string; type: PortType; hint: string; inspect?: boolean; frozen?: boolean; last?: boolean;
}) {
  return (
    <div className={cn('relative flex h-11 w-full flex-wrap items-center justify-between bg-muted px-5 py-2', last && 'rounded-b-[0.69rem]')} title={hint}>
      <div className="flex w-full items-center justify-end truncate text-sm">
        <div className="flex flex-1" />
        {frozen ? <Snowflake className="mr-1 h-3 w-3 text-[#3ba0ff]" /> : null}
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 text-sm font-medium">{label}</span>
          {inspect ? (
            <ShadTooltip content="Inspect output">
              <Button variant="ghost" size="icon" className="h-6 w-6 nodrag" aria-label="Inspect output"
                onClick={() => { if (nodeId) emitNodeAction(nodeId, 'docs'); }}>
                <TextSearch className="h-4 w-4 text-muted-foreground" />
              </Button>
            </ShadTooltip>
          ) : null}
        </div>
      </div>
      <Handle type="source" id={name} position={Position.Right} className="lf-handle out" style={handleStyle(type)} title={hint} />
    </div>
  );
}

// Capability nodes have a polymorphic output set (message/data/files/out) → one
// adaptive "out" port. Control-flow nodes (branch true/false, loop/map item/done)
// have distinct named outputs → one row + handle per output (like Langflow).
function OutputPorts({ nodeId, outputs, ioType, frozen }: { nodeId?: string; outputs?: PortSpec[]; ioType?: PortType; frozen?: boolean }) {
  const list = outputs ?? [];
  const adaptive = list.length > 1 && list.some((port) => port.name === 'out');
  if (adaptive || list.length <= 1) {
    const port = list[0] ?? { name: 'out', label: 'Result', type: 'any' as PortType };
    const type: PortType = adaptive ? 'any' : (ioType ?? port.type);
    const label = adaptive ? 'Output' : port.label;
    const hint = adaptive
      ? 'Output — the sub-value is chosen by what you connect it to (text→message, object→data, list→files)'
      : `${label} · ${type}`;
    return <OutputRow nodeId={nodeId} name={adaptive ? 'out' : port.name} label={label} type={type} hint={hint} inspect frozen={frozen} last />;
  }
  return (
    <>
      {list.map((port, index) => (
        <OutputRow key={port.name} nodeId={nodeId} name={port.name} label={port.label} type={port.type}
          hint={`${port.label} · ${port.type}`} frozen={frozen && index === 0} last={index === list.length - 1} />
      ))}
    </>
  );
}

/** Selected-node action bar (Langflow's nodeToolbarComponent pattern). Node
 * components have no app handlers, so actions travel as a DOM CustomEvent
 * that the canvas root listens for. */
export const NODE_ACTION_EVENT = 'canvas-node-action';
export type NodeAction = 'run' | 'save' | 'duplicate' | 'copy' | 'docs' | 'minimize' | 'freeze' | 'download' | 'delete';
function emitNodeAction(nodeId: string, action: NodeAction) {
  window.dispatchEvent(new CustomEvent(NODE_ACTION_EVENT, { detail: { nodeId, action } }));
}

// Header run/status cluster copied from Langflow's NodeStatus: a right-aligned
// Play button (Loader2 while running) preceded by a run-count badge in the same
// emerald/font-mono treatment Langflow uses for its duration/token badge.
function NodeRunStatus({ id, state, count, editable }: { id: string; state?: CanvasData['runState']; count?: number; editable?: boolean }) {
  const running = state === 'running';
  return (
    <div className="ml-auto flex shrink-0 items-center gap-1.5">
      {count && count > 1 ? (
        <span className={cn('flex items-center gap-1 rounded-sm px-1 font-mono text-xs',
          state === 'failed' ? 'text-destructive' : 'text-accent-emerald-foreground')}>×{count}</span>
      ) : null}
      {editable ? (
        <ShadTooltip content="Edit configuration">
          <Button
            unstyled
            className="nodrag flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            onClick={() => emitNodeAction(id, 'docs')}
            aria-label="Edit configuration"
          >
            <SlidersHorizontal className="h-3.5 w-3.5" strokeWidth={2} />
          </Button>
        </ShadTooltip>
      ) : null}
      <ShadTooltip content="Run flow">
        <Button
          unstyled
          className="nodrag flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          onClick={() => emitNodeAction(id, 'run')}
          aria-label="Run flow"
        >
          {running
            ? <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-emerald-foreground" />
            : <Play className="h-3.5 w-3.5" strokeWidth={2} />}
        </Button>
      </ShadTooltip>
    </div>
  );
}

/** Selected-node action bar: quick Duplicate/Delete plus a ⋯ menu (Langflow's
 * nodeToolbarComponent). ``minimized`` flips the Minimize item to Expand. */
function CardToolbar({ id, visible, minimized, frozen }: { id: string; visible: boolean; minimized?: boolean; frozen?: boolean }) {
  // The ⋯ menu is controlled so a right-click on the node (canvas-node-menu
  // event, dispatched by onNodeContextMenu) can open it — Langflow's
  // openDropdownOnRightClick.
  const [menuOpen, setMenuOpen] = useState(false);
  useEffect(() => {
    const onMenu = (event: Event) => {
      if ((event as CustomEvent<{ nodeId: string }>).detail?.nodeId === id) setMenuOpen(true);
    };
    window.addEventListener('canvas-node-menu', onMenu);
    return () => window.removeEventListener('canvas-node-menu', onMenu);
  }, [id]);
  return (
    <NodeToolbar isVisible={visible} position={Position.Top} offset={8}>
      <div className="lf-node-toolbar">
        <ShadTooltip content={frozen ? 'Unfreeze (recompute)' : 'Freeze (reuse last output)'}><Button variant="ghost" size="node-toolbar" className={frozen ? 'text-[#3ba0ff]' : ''} onClick={() => emitNodeAction(id, 'freeze')}><Snowflake /></Button></ShadTooltip>
        <ShadTooltip content="Duplicate (Ctrl+D)"><Button variant="ghost" size="node-toolbar" onClick={() => emitNodeAction(id, 'duplicate')}><Copy /></Button></ShadTooltip>
        <ShadTooltip content={minimized ? 'Expand' : 'Minimize'}><Button variant="ghost" size="node-toolbar" onClick={() => emitNodeAction(id, 'minimize')}>{minimized ? <Maximize2 /> : <Minimize2 />}</Button></ShadTooltip>
        <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
          <DropdownMenuTrigger asChild><Button variant="ghost" size="node-toolbar"><MoreHorizontal /></Button></DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-44 nodrag nowheel">
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'save')}><Save className="mr-2 h-4 w-4" />Save flow<DropdownMenuShortcut>⌘S</DropdownMenuShortcut></DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'freeze')}><Snowflake className="mr-2 h-4 w-4" />{frozen ? 'Unfreeze' : 'Freeze'}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'duplicate')}><Copy className="mr-2 h-4 w-4" />Duplicate<DropdownMenuShortcut>⌘D</DropdownMenuShortcut></DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'copy')}><ClipboardCopy className="mr-2 h-4 w-4" />Copy<DropdownMenuShortcut>⌘C</DropdownMenuShortcut></DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'docs')}><FileText className="mr-2 h-4 w-4" />Docs</DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'minimize')}>{minimized ? <Maximize2 className="mr-2 h-4 w-4" /> : <Minimize2 className="mr-2 h-4 w-4" />}{minimized ? 'Expand' : 'Minimize'}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => emitNodeAction(id, 'download')}><Download className="mr-2 h-4 w-4" />Download<DropdownMenuShortcut>⌘J</DropdownMenuShortcut></DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem className="text-destructive focus:text-destructive" onClick={() => emitNodeAction(id, 'delete')}><Trash2 className="mr-2 h-4 w-4" />Delete<DropdownMenuShortcut>⌫</DropdownMenuShortcut></DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </NodeToolbar>
  );
}

// Editable node title copied from Langflow's NodeName: a static title with a
// pencil (shown on select) that swaps it for an Input. The custom name is
// stored as `data.name` — separate from the `${id}` reference — and falls back
// to the spec label when empty.
function EditableNodeName({ id, name, fallback, selected, update }: {
  id: string; name?: string; fallback: string; selected?: boolean; update: CanvasData['update'];
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(name ?? '');
  useEffect(() => { if (!editing) setDraft(name ?? ''); }, [name, editing]);
  const commit = () => { update(id, { name: draft.trim() || undefined }); setEditing(false); };
  if (editing) {
    return (
      <Input autoFocus value={draft} className="nodrag h-6 min-w-0 flex-1 px-1.5 py-0 text-base"
        onChange={(event) => setDraft(event.target.value)}
        onBlur={commit}
        onKeyDown={(event) => {
          if (event.key === 'Enter') { event.preventDefault(); commit(); }
          else if (event.key === 'Escape') { setDraft(name ?? ''); setEditing(false); }
        }} />
    );
  }
  return (
    <>
      <strong>{name || fallback}</strong>
      {selected ? (
        <ShadTooltip content="Rename">
          <Button unstyled className="nodrag flex h-5 w-5 shrink-0 items-center justify-center rounded text-muted-foreground transition-colors hover:text-foreground"
            aria-label="Rename node" onClick={() => setEditing(true)}>
            <PencilLine className="h-3.5 w-3.5" />
          </Button>
        </ShadTooltip>
      ) : null}
    </>
  );
}

export function FieldShell({ label, required, hint, handle, children }: { label: string; required?: boolean; hint?: string; handle?: React.ReactNode; children: React.ReactNode }) {
  // Markup copied from Langflow's NodeInputField: a min-h-10 px-5 py-2 row with
  // the handle on the left edge, then a flex-col of the label row + control.
  return (
    <div className="relative flex min-h-10 w-full items-center justify-between px-5 py-2">
      {handle}
      <div className="flex w-full min-w-0 flex-col gap-2">
        <div className="flex w-full items-center text-sm">
          <span className="truncate text-sm font-medium text-foreground">{label}</span>
          {required ? <span className="ml-0.5 text-destructive">*</span> : null}
          {hint ? (
            <ShadTooltip content={hint} side="top">
              <Info strokeWidth={1.5} className="ml-1 h-3 w-3 shrink-0 cursor-help text-muted-foreground" />
            </ShadTooltip>
          ) : null}
        </div>
        {children}
      </div>
    </div>
  );
}

export function ParamControl({ param, value, onChange }: { param: ParamSpec; value: string; onChange: (name: string, value: string) => void }) {
  if (param.type === 'boolean') {
    return <Switch checked={value === 'true'} onCheckedChange={(checked) => onChange(param.name, checked ? 'true' : '')} />;
  }
  if (param.type === 'select') {
    return (
      <Select value={value || undefined} onValueChange={(next) => onChange(param.name, next)}>
        <SelectTrigger className="h-8 text-xs nodrag"><SelectValue placeholder="Select…" /></SelectTrigger>
        <SelectContent>{(param.options ?? []).map((option) => <SelectItem key={option} value={option} className="text-xs">{option}</SelectItem>)}</SelectContent>
      </Select>
    );
  }
  if (param.multiline || param.type === 'json') {
    return <Textarea rows={2} className="min-h-0 px-2.5 py-1.5 text-xs" value={value} spellCheck={false} placeholder={param.type === 'json' ? '{ }' : 'Type something…'} onChange={(event) => onChange(param.name, event.target.value)} />;
  }
  return <Input type={param.type === 'number' ? 'number' : 'text'} className="h-8 px-2.5 text-xs" value={value} placeholder="Type something…" onChange={(event) => onChange(param.name, event.target.value)} />;
}

/** Structural specs edit `target`/`attrs`; capability specs edit `args`. */
export function paramAccess(id: string, data: CanvasData) {
  const spec = data.spec;
  const paramValue = (param: ParamSpec): string => {
    if (spec?.category === 'structural') return param.name === 'target' ? data.target ?? '' : data.attrs[param.name] ?? '';
    return data.args[param.name] ?? '';
  };
  const setParam = (name: string, value: string) => data.update(id, (current) => {
    if (spec?.category === 'structural') return name === 'target' ? { target: value } : { attrs: { ...current.attrs, [name]: value } };
    return { args: { ...current.args, [name]: value } };
  });
  return { paramValue, setParam };
}

function StepNodeCard({ id, data, selected }: NodeProps<CanvasNode>) {
  const spec = data.spec;
  const { paramValue, setParam } = paramAccess(id, data);
  return (
    <div className={`lf-node${runClass(data)}${selected ? ' selected' : ''}${data.minimized ? ' lf-minimized' : ''}${data.frozen ? ' lf-frozen' : ''}`}>
      <CardToolbar id={id} visible={Boolean(selected)} minimized={data.minimized} frozen={data.frozen} />
      <header className="lf-node-head">
        <NodeIcon name={spec?.icon} category={spec?.category ?? 'tool'} size={18} className="lf-head-icon" />
        <EditableNodeName id={id} name={data.name} fallback={spec?.label ?? data.stepType ?? 'Step'} selected={Boolean(selected)} update={data.update} />
        {data.frozen ? <Snowflake size={12} className="lf-frozen-badge" /> : null}
        <code className="lf-node-ref" title="Reference this step in task text">{'$'}{'{'}{id}{'}'}</code>
        <NodeRunStatus id={id} state={data.runState} count={data.runCount} editable />
      </header>
      {!data.minimized && spec?.description ? <p className="lf-node-desc">{spec.description}</p> : null}
      {!data.minimized ? <div className="lf-node-body nodrag nowheel">
        {spec?.has_items || data.items ? (
          <FieldShell label="Items" hint="A list to iterate: connect a step or type ${...}"
            handle={<InHandle id="items" type={inputPortType(spec, 'items')} />}>
            {data.boundParams.has('items')
              ? <span className="lf-bound">Connected</span>
              : <Input className="h-8 px-2.5 text-xs" value={data.items} placeholder="${inputs.list}" onChange={(event) => data.update(id, { items: event.target.value })} />}
          </FieldShell>
        ) : null}
        {spec?.has_task || data.task ? (
          <FieldShell label="Task" hint="Instruction text; embed results with ${step_id} and inputs with ${inputs.name}"
            handle={<InHandle id="task" type={inputPortType(spec, 'task')} />}>
            {data.boundParams.has('task')
              ? <span className="lf-bound">Connected</span>
              : <Textarea rows={3} className="min-h-0 px-2.5 py-1.5 text-xs" value={data.task} spellCheck={false} placeholder="Type something…" onChange={(event) => data.update(id, { task: event.target.value })} />}
          </FieldShell>
        ) : null}
        {(spec?.params ?? []).map((param) => (
          <FieldShell key={param.name} label={param.label} required={param.required} hint={param.description}
            handle={param.connectable ? <InHandle id={`arg:${param.name}`} type={inputPortType(spec, `arg:${param.name}`)} /> : undefined}>
            {data.boundParams.has(`arg:${param.name}`)
              ? <span className="lf-bound">Connected</span>
              : <ParamControl param={param} value={paramValue(param)} onChange={setParam} />}
          </FieldShell>
        ))}
        <AgentMountsSection id={id} spec={spec} mounts={data.mounts} boundParams={data.boundParams} update={data.update} />
      </div> : null}
      {data.minimized ? <MinimizedHandles inputs={spec?.inputs} /> : null}
      <OutputPorts nodeId={id} outputs={spec?.outputs} frozen={data.frozen} />
      {data.runState === 'failed' ? <p className="lf-node-error">Failed — open the panel for details</p> : null}
    </div>
  );
}

/** Capability mounts folded into one collapsible "Capabilities" section so the
 * agent node stays compact. Collapsed shows a header + summary (how many kinds
 * are mounted, "Defaults" if none); expanded reveals one box per type — wire
 * capability nodes into the handle, OR click the box to multi-select from the
 * roster. Every agent can mount tools/skills/connectors/workflows/environments/
 * agents. Collapsed hides the mount handles entirely (folded away); it opens by
 * default whenever anything is mounted, so wired edges stay visible. */
function AgentMountsSection({ id, spec, mounts, boundParams, update }: {
  id: string; spec?: NodeSpec; mounts: Record<string, string[]>;
  boundParams: Set<string>; update: CanvasData['update'];
}) {
  const ports = (spec?.inputs ?? []).filter((port) => port.name.startsWith('mount:'));
  const active = ports.reduce((sum, port) => {
    const mountType = port.name.slice('mount:'.length);
    return sum + (boundParams.has(port.name) || (mounts[mountType]?.length ?? 0) > 0 ? 1 : 0);
  }, 0);
  const [open, setOpen] = useState(active > 0);
  if (!ports.length) return null;
  return (
    <div className={`lf-mounts${open ? ' open' : ''}`}>
      <button type="button" className="lf-mounts-head nodrag" onClick={() => setOpen((value) => !value)} aria-expanded={open}>
        {open ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        <span className="lf-mounts-title">Capabilities</span>
        <span className="lf-mounts-summary">{active ? `${active} mounted` : 'Defaults'}</span>
      </button>
      {open ? (
        <div className="lf-mounts-body">
          {ports.map((port) => {
            const mountType = port.name.slice('mount:'.length);
            return (
              <FieldShell key={port.name} label={port.label}
                hint={`Wire ${port.label.toLowerCase()} nodes in, or click to pick`}
                handle={<InHandle id={port.name} type={inputPortType(spec, port.name)} />}>
                <MountPicker type={mountType} label={port.label}
                  selected={mounts[mountType] ?? []}
                  connected={boundParams.has(port.name)}
                  onChange={(next) => update(id, (current) => ({ mounts: { ...current.mounts, [mountType]: next } }))} />
              </FieldShell>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/** When a node is collapsed, its per-field input handles are gone with the body,
 * so edges would float. Re-render just the handle dots stacked on the left edge
 * (same ids the edges bind to) so connections stay anchored. */
function MinimizedHandles({ inputs }: { inputs?: PortSpec[] }) {
  const ports = inputs ?? [];
  if (!ports.length) return null;
  return (
    <>
      {ports.map((port, index) => (
        <Handle key={port.name} type="target" id={port.name} position={Position.Left}
          className="lf-handle in lf-min-handle" style={handleStyle(port.type, { top: `${((index + 1) / (ports.length + 1)) * 100}%` })}
          title={`${port.label} · ${port.type}`} />
      ))}
    </>
  );
}

function IoNodeCard({ id, data, selected }: NodeProps<CanvasNode>) {
  const isInput = data.type === 'input';
  const io = data.io;
  const set = (patch: Partial<CanvasData['io']>) => data.update(id, (current) => ({ io: { ...current.io, ...patch } }));
  return (
    <div className={`lf-node lf-io${selected ? ' selected' : ''}`}>
      <CardToolbar id={id} visible={Boolean(selected)} minimized={data.minimized} frozen={data.frozen} />
      <header className="lf-node-head">
        <NodeIcon name="MessagesSquare" category="io" size={18} className="lf-head-icon" />
        <strong>{isInput ? 'Chat Input' : 'Chat Output'}</strong>
        {isInput && io.name ? <code className="lf-node-ref">{'$'}{'{'}inputs.{io.name}{'}'}</code> : null}
        <NodeRunStatus id={id} state={data.runState} count={data.runCount} />
      </header>
      <div className="lf-node-body nodrag nowheel">
        <FieldShell label="Name" required><Input className="h-8 px-2.5 text-xs" value={io.name} placeholder="name" onChange={(event) => set({ name: event.target.value })} /></FieldShell>
        {isInput ? <>
          <FieldShell label="Type"><Select value={io.input_type} onValueChange={(next) => set({ input_type: next })}><SelectTrigger className="h-8 text-xs nodrag"><SelectValue /></SelectTrigger><SelectContent>{['string', 'number', 'boolean', 'array', 'object'].map((option) => <SelectItem key={option} value={option} className="text-xs">{option}</SelectItem>)}</SelectContent></Select></FieldShell>
          <FieldShell label="Required"><Switch checked={io.required} onCheckedChange={(checked) => set({ required: checked })} /></FieldShell>
        </> : (
          <FieldShell label="Value" handle={<InHandle id="value" type="any" />}>
            {data.boundParams.has('value')
              ? <span className="lf-bound">Connected</span>
              : <Input className="h-8 px-2.5 text-xs" value={io.value} placeholder="${step_id}" onChange={(event) => set({ value: event.target.value })} />}
          </FieldShell>
        )}
      </div>
      {isInput ? <OutputPorts nodeId={id} outputs={data.spec?.outputs} ioType={IO_INPUT_PORT[io.input_type] ?? 'any'} /> : null}
    </div>
  );
}

// Sticky note — Langflow NoteNode: a resizable colored card with editable
// markdown-ish text and a select-only color/delete toolbar. Purely visual; the
// serializer stores notes separately so they never enter the compiled graph.
const NOTE_ORDER: NoteColor[] = ['amber', 'neutral', 'rose', 'blue', 'lime'];
const NOTE_BG: Record<NoteColor, string> = {
  amber: 'hsl(48 96% 77%)', neutral: 'hsl(240 5% 88%)', rose: 'hsl(347 77% 86%)', blue: 'hsl(214 95% 86%)', lime: 'hsl(85 78% 80%)',
};

function NoteNodeCard({ id, data, selected }: NodeProps<CanvasNode>) {
  const note = data.note ?? { text: '', color: 'amber' as NoteColor };
  return (
    <>
      <NodeResizer minWidth={180} minHeight={110} isVisible={Boolean(selected)}
        lineClassName="!border !border-muted-foreground" handleClassName="!h-2 !w-2 !rounded-sm !border !border-muted-foreground !bg-background" />
      {selected ? (
        <NodeToolbar isVisible position={Position.Top} offset={8}>
          <div className="lf-node-toolbar">
            {NOTE_ORDER.map((color) => (
              <button key={color} type="button" aria-label={color}
                className={cn('h-4 w-4 rounded-full border border-black/20', note.color === color && 'ring-2 ring-offset-1 ring-primary')}
                style={{ background: NOTE_BG[color] }}
                onClick={() => data.update(id, { note: { ...note, color } })} />
            ))}
            <ShadTooltip content="Delete note"><Button variant="ghost" size="node-toolbar" className="text-destructive" onClick={() => emitNodeAction(id, 'delete')}><Trash2 /></Button></ShadTooltip>
          </div>
        </NodeToolbar>
      ) : null}
      <div className="lf-note" style={{ background: NOTE_BG[note.color] ?? NOTE_BG.amber }}>
        <textarea
          className="lf-note-text nodrag nowheel"
          value={note.text}
          spellCheck={false}
          placeholder="Write a note…"
          onChange={(event) => data.update(id, { note: { ...note, text: event.target.value } })}
        />
      </div>
    </>
  );
}

export const NODE_TYPES = { stepNode: StepNodeCard, ioNode: IoNodeCard, noteNode: NoteNodeCard };
