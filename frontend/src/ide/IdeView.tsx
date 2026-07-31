import { useCallback, useEffect, useRef, useState } from 'react';
import { Loader2, RefreshCw, SquareTerminal } from 'lucide-react';

import { Button } from '../components/ui/button';
import type { RequestFn } from '../canvas/types';
// Owned here rather than in canvas.css: both are lazy modules, so parking the
// IDE's styles there left this view unstyled until the canvas had been opened.
import '../style/ide.css';

/** Keep-alive cadence. The manager also refreshes the idle clock on every
 *  proxied request, so this only matters while the IDE sits untouched. */
const HEARTBEAT_MS = 60_000;

interface IdeStatus { running: boolean; path?: string }

/** Full VS Code for the current session, embedded in an iframe.
 *
 * The IDE is served under a path on THIS origin (`/ide/<session>/`), so it is
 * reachable at whatever address the browser reached the UI at — a tunnel, a
 * reverse proxy, or plain localhost. openvscode-server is started with that
 * path as its base so its absolute asset URLs match; see
 * autogenesis/ide/README.md. The container starts lazily on first open and is
 * reaped once idle, so mounting this view is what boots it. */
export function IdeView({ request, sessionId, connected, status, statusText, onOpenNav }: {
  request: RequestFn;
  sessionId?: string;
  connected: boolean;
  status?: string;
  statusText?: string;
  onOpenNav?: () => void;
}) {
  const [path, setPath] = useState<string>();
  const [error, setError] = useState<string>();
  const [starting, setStarting] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);

  const start = useCallback(async () => {
    if (!sessionId || !connected) return;
    setStarting(true);
    setError(undefined);
    try {
      const response = await request('ide.start', { session_id: sessionId });
      if (!response.ok) throw new Error(response.error?.message ?? 'Could not start the IDE');
      const status = response.result as unknown as IdeStatus;
      if (!status.path) throw new Error('The gateway did not return an IDE address');
      setPath(status.path);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setStarting(false);
    }
  }, [request, sessionId, connected]);

  // Boot on mount / session switch. The first call pulls or builds a ~600MB
  // image, so this can take a while before the iframe appears.
  useEffect(() => { setPath(undefined); void start(); }, [start]);

  // Heartbeat so an open-but-idle IDE is not reaped underneath the user.
  const pathRef = useRef<string | undefined>(undefined);
  pathRef.current = path;
  useEffect(() => {
    if (!sessionId || !connected) return;
    const timer = window.setInterval(() => {
      if (pathRef.current) void request('ide.status', { session_id: sessionId });
    }, HEARTBEAT_MS);
    return () => window.clearInterval(timer);
  }, [request, sessionId, connected]);

  if (!sessionId) return <IdeNotice title="No session" detail="Open or create a session to use the editor." />;
  if (error) {
    return (
      <IdeNotice title="The IDE could not start" detail={error}>
        <Button size="md" className="font-normal" onClick={() => void start()}>Try again</Button>
      </IdeNotice>
    );
  }
  if (!path || starting) {
    return (
      <IdeNotice
        title="Starting VS Code…"
        detail="Booting this session's editor container. The first launch also builds the image and installs the Claude Code and Codex extensions, which can take a few minutes; later sessions reuse both."
        spinning
      />
    );
  }

  // Same-origin and relative: whatever address this page was loaded from is the
  // one the iframe uses. ?folder= opens the mounted workspace — the same files
  // the agent edits.
  const src = `${path}?folder=/workspace`;
  return (
    <div className="ide-view">
      {/* The only chrome above the editor — VS Code supplies the rest, so this
          stays one slim row instead of the usual eyebrow+title page header. */}
      <header className="ide-toolbar">
        {onOpenNav ? <button className="mobile-menu" onClick={onOpenNav} aria-label="Open navigation">☰</button> : null}
        <SquareTerminal size={14} strokeWidth={1.9} />
        <strong>Code</strong>
        <code className="ide-origin" title="This session's IDE path">{path}</code>
        <span className="ide-toolbar-spacer" />
        {statusText ? <span className="ide-status"><span className={`connection-dot ${status ?? ''}`} />{statusText}</span> : null}
        <Button variant="ghost" size="sm" className="font-normal" onClick={() => setReloadKey((key) => key + 1)}>
          <RefreshCw /> Reload
        </Button>
      </header>
      <iframe
        key={reloadKey}
        className="ide-frame"
        title="VS Code"
        src={src}
        // No sandbox attribute: VS Code's webviews and service worker need
        // same-origin scripting, and this frame is our own trusted container.
        allow="clipboard-read; clipboard-write"
      />
    </div>
  );
}

function IdeNotice({ title, detail, spinning, children }: {
  title: string; detail: string; spinning?: boolean; children?: React.ReactNode;
}) {
  return (
    <div className="ide-notice">
      {spinning ? <Loader2 className="ide-spinner" /> : null}
      <strong>{title}</strong>
      <p>{detail}</p>
      {children}
    </div>
  );
}
