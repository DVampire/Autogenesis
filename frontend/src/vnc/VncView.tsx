import { useEffect, useRef, useState } from 'react';
// noVNC is heavy; this module is loaded lazily (see EnvironmentLive) so it stays
// out of the main bundle until a live VNC view actually appears.
import RFB from '@novnc/novnc';

// noVNC's RFB exposes focus() at runtime, but the bundled types omit it.
type FocusableRFB = RFB & { focus?: () => void };
const focusRfb = (rfb: RFB | null | undefined) => { try { (rfb as FocusableRFB | null)?.focus?.(); } catch { /* canvas not ready */ } };

/**
 * Render a live VNC stream (RFB over WebSocket) onto a canvas noVNC manages.
 * Frames flow browser ↔ gateway relay ↔ websockify.
 *
 * Two modes, toggled by the "接管/Take over" button:
 *  - watch (default): viewOnly, so you only observe what the agent does;
 *  - interactive: mouse + keyboard are sent to the container, so you can drive
 *    the browser yourself. (You and the agent share one cursor — take over only
 *    when the agent is idle.)
 */
export default function VncView({ url, password }: { url: string; password?: string | null }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const rfbRef = useRef<RFB | null>(null);
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting');
  const [interactive, setInteractive] = useState(false);

  useEffect(() => {
    const target = containerRef.current;
    if (!target) return;
    setStatus('connecting');
    let rfb: RFB | undefined;
    try {
      rfb = new RFB(target, url, password ? { credentials: { password } } : undefined);
      rfb.scaleViewport = true;      // fit the stream to the card
      rfb.clipViewport = false;
      rfb.viewOnly = !interactive;   // start read-only unless the user took over
      rfb.addEventListener('connect', () => setStatus('connected'));
      rfb.addEventListener('disconnect', () => setStatus('disconnected'));
      rfbRef.current = rfb;
    } catch {
      setStatus('disconnected');
    }
    return () => { rfbRef.current = null; try { rfb?.disconnect(); } catch { /* already gone */ } };
    // Reconnect only on url/password change — the mode toggle is applied live below.
  }, [url, password]);

  // Apply the mode to the live connection without reconnecting.
  useEffect(() => {
    const rfb = rfbRef.current;
    if (!rfb) return;
    rfb.viewOnly = !interactive;
    if (interactive && status === 'connected') {
      focusRfb(rfb);
    }
  }, [interactive, status]);

  return (
    <div className="vnc-view">
      <div
        className={`vnc-canvas${interactive ? ' interactive' : ''}`}
        ref={containerRef}
        onMouseEnter={() => { if (interactive) focusRfb(rfbRef.current); }}
      />
      {status === 'connected' ? (
        <button
          type="button"
          className={`vnc-takeover${interactive ? ' on' : ''}`}
          onClick={() => setInteractive((v) => !v)}
          title={interactive ? '交还给 agent（回到只看）' : '接管浏览器（可用鼠标键盘操作）'}
        >
          {interactive ? '● 操作中 · 交还' : '接管'}
        </button>
      ) : null}
      {status !== 'connected'
        ? <div className="vnc-overlay">{status === 'connecting' ? 'Connecting to live view…' : 'Live view disconnected'}</div>
        : null}
    </div>
  );
}
