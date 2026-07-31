import { useCallback, useEffect, useRef, useState } from 'react';
import { Cpu, FlaskConical, HardDrive, Loader2, MemoryStick, NotebookPen, SquareArrowOutUpRight, Zap } from 'lucide-react';

import { Button } from '../components/ui/button';
import type { RequestFn } from '../canvas/types';
import type { GatewayEvent } from '../controllers/gateway';
import { ScienceConversation } from './Conversation';
import { KernelPanel } from './KernelPanel';
// Owned here rather than in canvas.css: both are lazy modules, so parking these
// styles there would leave this view unstyled until the canvas had been opened.
import '../style/science.css';

/** Keep-alive cadence. The manager also refreshes the idle clock on every
 *  proxied request, so this only matters while the Lab sits untouched. */
const HEARTBEAT_MS = 60_000;
/** How often the Compute panel re-reads the workstation. Slow on purpose: each
 *  poll is a `docker exec` into the container, and GPU memory over a training
 *  run is a curve, not something you watch tick. */
const COMPUTE_MS = 15_000;

interface ScienceStatus { running: boolean; path?: string; gpus?: string }
interface Gpu { index: number; name: string; memory_used_mb: number; memory_total_mb: number; utilization_percent: number }
interface Compute {
  running: boolean; busy: boolean; gpus: Gpu[];
  cpu_count?: number | null; memory_total_mb?: number | null; memory_used_mb?: number | null;
  disk_free_mb?: number | null; executions: number;
}

/** The Science workstation: a conversation with the agent, over a shared kernel.
 *
 * There is no science container. Everything runs in the base environment, so
 * the agent's code_interpreter_tool, the Notebook tab's REPL and JupyterLab all
 * go through ONE kernel — a variable the agent defined is one you can print.
 * See autogenesis/science/README.md.
 *
 * JupyterLab is served under a path on THIS origin (`/science/<session>/`), so
 * it is reachable at whatever address the browser reached the UI at: a tunnel,
 * a reverse proxy, or plain localhost. */
export function ScienceView({ request, subscribe, sessionId, connected, status, statusText, onOpenNav }: {
  request: RequestFn;
  subscribe: (listener: (event: GatewayEvent) => void) => () => void;
  sessionId?: string;
  connected: boolean;
  status?: string;
  statusText?: string;
  onOpenNav?: () => void;
}) {
  const [path, setPath] = useState<string>();
  const [error, setError] = useState<string>();
  const [compute, setCompute] = useState<Compute>();
  // Compute and Notebook are alternatives, not a stack: both stacked meant
  // neither had room, and only one of them answers any given question.
  const [tab, setTab] = useState<'compute' | 'notebook'>('notebook');

  const start = useCallback(async () => {
    if (!sessionId || !connected) return;
    setError(undefined);
    try {
      const response = await request('science.start', { session_id: sessionId });
      if (!response.ok) throw new Error(response.error?.message ?? 'Could not start the workstation');
      const result = response.result as unknown as ScienceStatus;
      if (!result.path) throw new Error('The gateway did not return a workstation address');
      setPath(result.path);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  }, [request, sessionId, connected]);

  useEffect(() => { setPath(undefined); void start(); }, [start]);

  const pathRef = useRef<string | undefined>(undefined);
  pathRef.current = path;
  useEffect(() => {
    if (!sessionId || !connected) return;
    const beat = window.setInterval(() => {
      if (pathRef.current) void request('science.status', { session_id: sessionId });
    }, HEARTBEAT_MS);
    return () => window.clearInterval(beat);
  }, [request, sessionId, connected]);

  // Not gated on the workstation: CPU, memory, disk and GPUs are the machine's,
  // readable the moment the view opens rather than half a minute later.
  useEffect(() => {
    if (!sessionId || !connected) return;
    let cancelled = false;
    const poll = async () => {
      const response = await request('science.compute', { session_id: sessionId });
      if (!cancelled && response.ok) setCompute(response.result as unknown as Compute);
    };
    void poll();
    const timer = window.setInterval(() => void poll(), COMPUTE_MS);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [request, sessionId, connected]);

  if (!sessionId) return <ScienceNotice title="No project" detail="Open or create a project to use the workstation." />;

  return (
    <div className="science-view">
      <header className="science-toolbar">
        {onOpenNav ? <button className="mobile-menu" onClick={onOpenNav} aria-label="Open navigation">☰</button> : null}
        <FlaskConical size={14} strokeWidth={1.9} />
        <strong>Science</strong>
        {path ? <code className="science-origin" title="This project's workstation path">{path}</code> : null}
        <span className="science-toolbar-spacer" />
        {statusText ? <span className="science-status"><span className={`connection-dot ${status ?? ''}`} />{statusText}</span> : null}
        {/* The full Lab, for what these cells deliberately do not do: interactive
            widgets, the debugger, extensions. Same server, same kernels — it is
            the other client of this workstation, not a different workstation. */}
        <Button variant="ghost" size="sm" className="font-normal" disabled={!path}
                title={path ? 'Open the full JupyterLab' : 'Starting the kernel…'}
                onClick={() => window.open(`${path}/lab`, '_blank', 'noopener')}>
          <SquareArrowOutUpRight /> JupyterLab
        </Button>
      </header>
      <div className="science-body">
        {/* The conversation is the surface, and it is available immediately —
            it needs no kernel. Gating the whole view on the workstation meant
            staring at a spinner for the ~11s a cold Jupyter Server takes before
            you could type a word. */}
        <ScienceConversation request={request} subscribe={subscribe}
                             sessionId={sessionId} connected={connected} />
        <aside className="science-rail">
          <div className="science-tabs" role="tablist">
            <button role="tab" aria-selected={tab === 'compute'} className={tab === 'compute' ? 'active' : ''}
                    onClick={() => setTab('compute')}><Cpu size={13} strokeWidth={1.9} /> Compute</button>
            <button role="tab" aria-selected={tab === 'notebook'} className={tab === 'notebook' ? 'active' : ''}
                    onClick={() => setTab('notebook')}><NotebookPen size={13} strokeWidth={1.9} /> Notebook</button>
          </div>
          {tab === 'compute' ? <ComputePanel compute={compute} /> :
            error ? <p className="science-rail-notice">{error} <button onClick={() => void start()}>Try again</button></p> :
            path ? <KernelPanel request={request} subscribe={subscribe} sessionId={sessionId} /> : (
              <p className="science-rail-notice">
                <Loader2 className="science-spinner inline" /> Starting this project's kernel.
                The first one boots a Jupyter Server — about ten seconds; after that a cell
                runs in milliseconds. You can talk to the agent meanwhile.
              </p>
            )}
        </aside>
      </div>
    </div>
  );
}

/** What the machine is running on.
 *
 * The base environment's own resources — the whole host, not a slice of it,
 * because that is exactly what the agent and the kernel get. */
function ComputePanel({ compute }: { compute?: Compute }) {
  const memoryPercent = compute?.memory_total_mb && compute?.memory_used_mb
    ? Math.round((compute.memory_used_mb / compute.memory_total_mb) * 100) : undefined;
  return (
    <section className="science-panel">
      {!compute ? <p className="empty">Reading the machine…</p> : (
        <>
          {/* GPUs are detected, not assumed: a host without an NVIDIA card is
              ordinary, and says so rather than showing an empty meter. */}
          {compute.gpus.length ? compute.gpus.map((gpu) => (
            <div className="compute-gpu" key={gpu.index}>
              <div className="compute-gpu-head"><Zap size={13} strokeWidth={1.9} /><strong>{gpu.name}</strong><em>#{gpu.index}</em></div>
              <Meter label="Memory" used={gpu.memory_used_mb} total={gpu.memory_total_mb} unit="MB" />
              <Meter label="Utilisation" used={gpu.utilization_percent} total={100} unit="%" />
            </div>
          )) : (
            <div className="compute-nogpu">
              <Zap size={13} strokeWidth={1.9} />
              <div>
                <strong>No GPU detected</strong>
                <p>This machine has no NVIDIA GPU available, so code runs on the CPU.</p>
              </div>
            </div>
          )}
          <div className="compute-row"><Cpu size={13} strokeWidth={1.9} /><span>CPU</span><em>{compute.cpu_count ?? '—'} cores</em></div>
          <div className="compute-row"><MemoryStick size={13} strokeWidth={1.9} /><span>Memory</span>
            <em>{memoryPercent === undefined ? '—' : `${gib(compute.memory_used_mb)} / ${gib(compute.memory_total_mb)} GiB`}</em></div>
          <div className="compute-row"><HardDrive size={13} strokeWidth={1.9} /><span>Disk free</span><em>{gib(compute.disk_free_mb)} GiB</em></div>
          <div className="compute-row">
            <span className="compute-uptime">
              {compute.running
                ? `Kernel ${compute.busy ? 'busy' : 'idle'} · ${compute.executions} cell${compute.executions === 1 ? '' : 's'} run`
                : 'Kernel not started'}
            </span>
          </div>
        </>
      )}
    </section>
  );
}

function Meter({ label, used, total, unit }: { label: string; used: number; total: number; unit: string }) {
  const percent = total ? Math.min(100, Math.round((used / total) * 100)) : 0;
  return (
    <div className="compute-meter">
      <div className="compute-meter-head"><span>{label}</span><em>{used}{unit === '%' ? '%' : ` / ${total} ${unit}`}</em></div>
      <div className="compute-meter-track"><div className="compute-meter-fill" style={{ width: `${percent}%` }} /></div>
    </div>
  );
}

function gib(megabytes?: number | null): string {
  return megabytes == null ? '—' : (megabytes / 1024).toFixed(1);
}

function ScienceNotice({ title, detail, spinning, children }: {
  title: string; detail: string; spinning?: boolean; children?: React.ReactNode;
}) {
  return (
    <div className="science-notice">
      {spinning ? <Loader2 className="science-spinner" /> : null}
      <strong>{title}</strong>
      <p>{detail}</p>
      {children}
    </div>
  );
}
