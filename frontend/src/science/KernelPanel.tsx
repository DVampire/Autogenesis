import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { CircleStop, Download, RotateCcw } from 'lucide-react';

import { Button } from '../components/ui/button';
import type { RequestFn } from '../canvas/types';
import type { GatewayEvent } from '../controllers/gateway';

export interface KernelOutput { type: string; name?: string | null; data: Record<string, string> }
export interface Execution {
  execution_count?: number | null; code: string; language: string;
  outputs: KernelOutput[]; success: boolean; error?: string | null;
  origin: 'agent' | 'user'; started_at: string; duration_ms?: number | null;
}
interface KernelState { running: boolean; busy: boolean; executions: number }

/** MIME types we render as something other than text, richest first — a bundle
 *  carries several representations of one thing. */
const RENDERERS = ['image/png', 'image/jpeg', 'image/svg+xml', 'text/html', 'text/markdown', 'application/json'] as const;
/** While the kernel is busy, re-read often enough that the agent's cells appear
 *  as it works; idle, back off so an open tab is not a poll loop. */
const POLL_BUSY_MS = 1500;
const POLL_IDLE_MS = 8000;

/** The notebook: this project's kernel history, plus a prompt into that kernel.
 *
 * Not a document. It is the kernel's own record of what has run — the agent's
 * cells and yours in one list, because both go through the same kernel, so
 * nothing has to be kept in sync.
 *
 * What it does NOT show is work the agent did some other way. The agent picks
 * its own tools, and for "write a function and test it" a shell is the natural
 * choice — bash_tool spawns a fresh process that has nothing to do with this
 * kernel. That is deliberate: the agent's behaviour is not bent to fill this
 * panel. The bridge is the workspace, which both sides share. */
export function KernelPanel({ request, subscribe, sessionId }: {
  request: RequestFn;
  subscribe: (listener: (event: GatewayEvent) => void) => () => void;
  sessionId: string;
}) {
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [kernel, setKernel] = useState<KernelState>({ running: false, busy: false, executions: 0 });
  const [draft, setDraft] = useState('');
  const [running, setRunning] = useState(false);
  const [live, setLive] = useState<KernelOutput[]>([]);
  const [notice, setNotice] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);

  // How many entries we hold, so a poll asks only for what is new. A history
  // with a few figures in it is megabytes of base64; refetching all of it every
  // few seconds while the agent works would be pure waste.
  const held = useRef(0);
  const load = useCallback(async () => {
    const response = await request('science.history', { session_id: sessionId, after: held.current });
    if (!response.ok) return;
    const body = response.result as unknown as {
      executions: Execution[]; status: KernelState; total: number; after: number;
    };
    setKernel(body.status);
    if (body.after !== held.current || body.total < held.current) {
      // The server trimmed, or restarted, and our cursor no longer lines up.
      held.current = body.executions.length;
      setExecutions(body.executions);
      return;
    }
    if (!body.executions.length) return;
    held.current = body.total;
    setExecutions((current) => [...current, ...body.executions]);
  }, [request, sessionId]);

  // Polled rather than pushed: the agent's cells go through the kernel, not
  // through this panel, so there is no event to ride. Fast while it is working.
  const busyRef = useRef(false);
  busyRef.current = kernel.busy || running;
  useEffect(() => {
    let cancelled = false;
    let timer: number;
    const tick = async () => {
      if (cancelled) return;
      await load();
      timer = window.setTimeout(tick, busyRef.current ? POLL_BUSY_MS : POLL_IDLE_MS);
    };
    void tick();
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [load]);

  // Your own cell streams while it runs, so a long loop prints as it goes.
  useEffect(() => subscribe((event) => {
    if (event.type !== 'science.output' || event.session_id !== sessionId) return;
    const output = (event.payload as { output?: KernelOutput }).output;
    if (output) setLive((current) => [...current, output]);
  }), [subscribe, sessionId]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [executions.length, live.length]);

  const submit = async () => {
    const code = draft.trim();
    if (!code || running) return;
    setRunning(true);
    setLive([]);
    setDraft('');
    const response = await request('science.run', { session_id: sessionId, code });
    if (!response.ok) setNotice(response.error?.message ?? 'The cell could not run');
    setRunning(false);
    setLive([]);
    await load();
  };

  const restart = async () => {
    await request('science.restart', { session_id: sessionId });
    setNotice('Kernel restarted — every variable is gone. The history below is what ran, not what is still live.');
    await load();
  };

  const save = async () => {
    const response = await request('science.save', { session_id: sessionId, name: 'session' });
    setNotice(response.ok
      ? `Saved to ${(response.result as { notebook?: { path?: string } }).notebook?.path}`
      : 'Could not save');
  };

  return (
    <div className="kernel-panel">
      <header className="kernel-bar">
        <span className={`kernel-dot ${kernel.busy || running ? 'busy' : kernel.running ? 'idle' : 'off'}`} />
        <span className="kernel-label">
          Python kernel{kernel.running ? ' · shared with the agent' : ' · not started'}
        </span>
        <span className="kernel-bar-spacer" />
        <em>{kernel.busy || running ? 'busy' : kernel.running ? 'idle' : '—'}</em>
        <Button variant="ghost" size="sm" className="font-normal" onClick={() => void request('science.interrupt', { session_id: sessionId })} disabled={!kernel.busy && !running}>
          <CircleStop /> Interrupt
        </Button>
        <Button variant="ghost" size="sm" className="font-normal" onClick={() => void restart()}>
          <RotateCcw /> Restart
        </Button>
        <Button variant="ghost" size="sm" className="font-normal" onClick={() => void save()} disabled={!executions.length}>
          <Download /> Save .ipynb
        </Button>
      </header>
      {notice ? <p className="kernel-notice" onClick={() => setNotice(undefined)}>{notice}</p> : null}

      <div className="kernel-history">
        {executions.length ? executions.map((entry, index) => (
          <Cell key={`${entry.started_at}:${index}`} entry={entry} />
        )) : (
          <p className="empty">Nothing has run yet. Type below to work in this project's
             kernel — it starts in the workspace, so anything the agent has written is
             importable straight away. The agent's own cells appear here too, on the runs
             where it reaches for the interpreter rather than a shell.</p>
        )}
        {running ? <Cell entry={{ code: '…', language: 'python', outputs: live, success: true, origin: 'user', started_at: '' }} pending /> : null}
        <div ref={bottom} />
      </div>

      <div className="kernel-prompt">
        <span className="kernel-caret">&gt;&gt;&gt;</span>
        <textarea
          value={draft}
          rows={1}
          spellCheck={false}
          placeholder="run code in this kernel…"
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); }
          }}
        />
      </div>
    </div>
  );
}

function Cell({ entry, pending }: { entry: Execution; pending?: boolean }) {
  return (
    <section className={`kernel-cell ${entry.origin}${entry.success ? '' : ' failed'}`}>
      <div className="kernel-cell-head">
        <span className="kernel-count">[{pending ? '*' : entry.execution_count ?? ' '}]</span>
        {/* Whose cell this was. Seeing what the AGENT ran is most of the point
            of the panel, so it is labelled rather than left to be guessed. */}
        <span className="kernel-origin">{entry.origin}</span>
        <span className="kernel-lang">{entry.language}</span>
        {entry.duration_ms ? <em>{formatDuration(entry.duration_ms)}</em> : null}
      </div>
      <pre className="kernel-code">{entry.code}</pre>
      {entry.outputs.length ? (
        <div className="kernel-outputs">
          {entry.outputs.map((output, index) => <Output key={index} output={output} />)}
        </div>
      ) : null}
    </section>
  );
}

function Output({ output }: { output: KernelOutput }) {
  const mime = useMemo(() => RENDERERS.find((candidate) => output.data[candidate]), [output]);
  const text = output.data['text/plain'] ?? '';

  if (output.type === 'error') return <pre className="kernel-output error">{text}</pre>;
  if (mime === 'image/png' || mime === 'image/jpeg') {
    return <img className="kernel-output image" alt="Cell output" src={`data:${mime};base64,${output.data[mime]}`} />;
  }
  if (mime === 'image/svg+xml') {
    // As an <img>, not inline: an SVG can carry script, and inlining it would
    // run that script on this app's origin, where the gateway connection lives.
    return <img className="kernel-output image" alt="Cell output"
                src={`data:image/svg+xml;base64,${btoa(unescape(encodeURIComponent(output.data[mime])))}`} />;
  }
  if (mime === 'text/html') {
    // Fully sandboxed: kernel output is not trusted content — a DataFrame holds
    // whatever the dataset holds. Scripts are off, so an interactive widget will
    // not draw here; that is what the JupyterLab button is for.
    return <iframe className="kernel-output html" sandbox="" title="Cell output" srcDoc={output.data[mime]} />;
  }
  if (mime === 'application/json') return <pre className="kernel-output">{output.data[mime]}</pre>;
  if (mime === 'text/markdown') return <pre className="kernel-output">{output.data[mime]}</pre>;
  return text ? <pre className={`kernel-output${output.name === 'stderr' ? ' stderr' : ''}`}>{text}</pre> : null;
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
  return `${(ms / 60_000).toFixed(1)}m`;
}
