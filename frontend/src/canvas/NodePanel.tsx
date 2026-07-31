import { X } from 'lucide-react';

import { Button } from '../components/ui/button';
import { Input } from '../components/ui/input';
import { Separator } from '../components/ui/separator';
import { ParamControl, paramAccess } from './nodes';
import type { CanvasNode, InvocationDoc, RunData } from './types';

function previewText(value: unknown): string {
  if (value === undefined || value === null) return '';
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return text.length > 20_000 ? `${text.slice(0, 20_000)}\n… (${text.length} chars)` : text;
}

function frameDuration(frame: { started_at?: string | null; finished_at?: string | null }): string {
  if (!frame.started_at || !frame.finished_at) return '';
  const ms = new Date(frame.finished_at).getTime() - new Date(frame.started_at).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
}

function PanelSection({ label, value }: { label: string; value: unknown }) {
  const text = previewText(value);
  if (!text) return null;
  return (
    <section className="panel-io">
      <header><strong>{label}</strong><Button variant="ghost" size="xs" onClick={() => navigator.clipboard?.writeText(text)}>Copy</Button></header>
      <pre>{text}</pre>
    </section>
  );
}

/** Langflow-style right panel: every parameter (including advanced runtime
 * attrs) plus the node's per-frame results from the last run. */
export function NodePanel({ node, runData, onClose }: { node: CanvasNode; runData?: RunData; onClose: () => void }) {
  const data = node.data;
  const spec = data.spec;
  const { paramValue, setParam } = paramAccess(node.id, data);
  const setAttr = (name: string, value: string) => data.update(node.id, (current) => ({ attrs: { ...current.attrs, [name]: value } }));

  const frames = Object.values(runData?.frames ?? {})
    .filter((frame) => frame.step_id === node.id)
    .sort((left, right) => (left.item_index ?? 0) - (right.item_index ?? 0) || (left.iteration ?? 0) - (right.iteration ?? 0));
  const invocationsByFrame = new Map<string, InvocationDoc[]>();
  for (const invocation of Object.values(runData?.invocations ?? {})) {
    const bucket = invocationsByFrame.get(invocation.frame_key);
    if (bucket) bucket.push(invocation); else invocationsByFrame.set(invocation.frame_key, [invocation]);
  }

  return (
    <aside className="node-panel nodrag nowheel">
      <header className="node-panel-head">
        <div>
          <h3>{spec?.label ?? node.id} <code>ID: {node.id}</code></h3>
          {spec?.description ? <p>{spec.description}</p> : null}
        </div>
        <Button variant="ghost" size="iconMd" className="ml-auto shrink-0" onClick={onClose} aria-label="Close panel"><X /></Button>
      </header>
      <div className="node-panel-body">
        {data.type === 'step' ? <>
          {(spec?.params ?? []).map((param) => (
            <div className="panel-field" key={param.name} title={param.description}>
              <span className="panel-field-label">{param.label}{param.required ? ' *' : ''}</span>
              {data.boundParams.has(`arg:${param.name}`)
                ? <span className="lf-bound">Connected</span>
                : <ParamControl param={param} value={paramValue(param)} onChange={setParam} />}
            </div>
          ))}
          <Separator className="my-1" />
          <div className="panel-field"><span className="panel-field-label">Retries</span>
            <Input type="number" min={0} className="h-8 text-xs" value={data.attrs.retries ?? ''} placeholder="0" onChange={(event) => setAttr('retries', event.target.value)} /></div>
          <div className="panel-field"><span className="panel-field-label">Timeout (s)</span>
            <Input type="number" min={0} className="h-8 text-xs" value={data.attrs.timeout ?? ''} placeholder="none" onChange={(event) => setAttr('timeout', event.target.value)} /></div>
        </> : null}
        {runData ? <p className="panel-run-heading">Last run</p> : null}
        {runData && !frames.length ? <p className="panel-empty">This step did not execute in the last run.</p> : null}
        {frames.map((frame) => {
          const invocations = invocationsByFrame.get(frame.key) ?? [];
          const title = [
            frame.item_index !== null && frame.item_index !== undefined ? `item ${frame.item_index}` : '',
            frame.iteration !== null && frame.iteration !== undefined ? `round ${frame.iteration}` : '',
          ].filter(Boolean).join(' · ') || 'execution';
          return (
            <details className={`panel-frame ${frame.state}`} key={frame.key} open={frames.length === 1}>
              <summary><span className={`frame-dot ${frame.state}`} /><strong>{title}</strong><em>{frame.state}</em><small>{frameDuration(frame)}</small></summary>
              {invocations.map((invocation) => (
                <div className="panel-invocation" key={invocation.key}>
                  <p className="panel-invocation-meta">
                    {invocation.capability_type}:{invocation.capability_name}
                    {invocation.cached ? ' · cached' : ''}
                    {invocation.token_cost ? ` · ${invocation.token_cost} tokens` : ''}
                    {invocation.attempts.length > 1 ? ` · ${invocation.attempts.length} attempts` : ''}
                  </p>
                  <PanelSection label="Input" value={invocation.input} />
                  <PanelSection label="Output" value={invocation.output} />
                  <PanelSection label="Error" value={invocation.error} />
                </div>
              ))}
              {!invocations.length ? <>
                <PanelSection label="Output" value={frame.output} />
                <PanelSection label="Error" value={frame.error} />
              </> : null}
            </details>
          );
        })}
      </div>
    </aside>
  );
}
