import http from 'node:http';
import net from 'node:net';
import type { Plugin } from 'vite';

// Routing for the per-session containers, by PATH for the service itself and by
// HOST for the other ports of the IDE's container.
//
//   /                       -> the Autogenesis SPA
//   /ide/<session>/         -> that session's VS Code
//   /science/<session>/     -> that project's JupyterLab
//
// Both services emit ABSOLUTE asset paths, so a sub-path only works if the
// server knows about it: openvscode-server is started with
// `--server-base-path /ide/<session>` and JupyterLab with
// `--ServerApp.base_url /science/<session>/`, which prefixes every URL each
// emits. Both sides then agree and this proxy has nothing to rewrite.
//
// They deliberately live on the UI's OWN origin. The previous scheme gave the
// editor a host of its own, `<session>.ide.localhost:5173`, which is resolved
// by the BROWSER — so it only ever worked when the browser ran on the machine
// serving the UI. Through any tunnel (Tailscale, an SSH -L to a different port,
// a reverse proxy) the iframe silently pointed at the user's own laptop.

// `/ide/<session>/…` and `/science/<session>/…` — each service knows its own
// prefix and emits it itself, so the capture is only used to pick the session.
const PATH_RE = /^\/(ide|science)\/([A-Za-z0-9_-]+)(?=[/?#]|$)/;
// `<port>-<session>.ide.localhost` reaches any OTHER port in that container — a
// dev server, a preview, an OAuth callback listener. Those services do not know
// they are proxied and have no base path to configure, so a host of their own is
// the only thing that keeps their absolute URLs working. Same caveat as above:
// `*.localhost` is loopback on the browser's machine, so this form is reachable
// only from a browser on the server (or through a forward of the UI port).
const HOST_RE = /^(?:(\d+)-)?([A-Za-z0-9_-]+)\.ide\.localhost(?::\d+)?$/;
const UPSTREAM_TTL_MS = 10_000;

const cache = new Map<string, { upstream: string; expires: number }>();

interface Target { service: 'ide' | 'science'; sessionId: string; port: number }

/** Parse a request into the session and container port it addresses — the URL
 *  path first (the editor), then the Host header (any other container port).
 *  Port 0 means "the IDE's own port", which the gateway resolves. */
function targetOf(req: { url?: string; headers: { host?: string } }): Target | null {
  const byPath = PATH_RE.exec(req.url ?? '');
  if (byPath) return { service: byPath[1] as 'ide' | 'science', sessionId: byPath[2], port: 0 };
  // The host form addresses the IDE container only: the science container
  // publishes exactly one port, and anything a notebook starts is reached
  // through jupyter-server-proxy on that same port.
  const byHost = HOST_RE.exec(req.headers.host ?? '');
  return byHost ? { service: 'ide', sessionId: byHost[2], port: byHost[1] ? Number(byHost[1]) : 0 } : null;
}

/** Ask the gateway which container serves this session, memoised briefly so a
 *  page load of ~100 assets does not trigger ~100 lookups. */
async function resolveUpstream(gatewayPort: string, target: Target): Promise<string | null> {
  const key = `${target.service}:${target.sessionId}:${target.port}`;
  const hit = cache.get(key);
  if (hit && hit.expires > Date.now()) return hit.upstream;
  try {
    const query = target.port ? `?port=${target.port}` : '';  // science takes no port
    const response = await fetch(`http://127.0.0.1:${gatewayPort}/${target.service}/resolve/${target.sessionId}${query}`);
    if (!response.ok) { cache.delete(key); return null; }
    const body = await response.json() as { upstream?: string };
    if (!body.upstream) return null;
    cache.set(key, { upstream: body.upstream, expires: Date.now() + UPSTREAM_TTL_MS });
    return body.upstream;
  } catch {
    return null;
  }
}

/** Split `http://host:port/proxy/3000` into the connection target plus the
 *  path prefix every forwarded request must carry. */
function parseUpstream(upstream: string): { host: string; port: number; prefix: string } {
  const url = new URL(upstream);
  return {
    host: url.hostname,
    port: Number(url.port || 80),
    prefix: url.pathname.replace(/\/$/, ''),
  };
}

export function containerProxy(gatewayPort: string): Plugin {
  return {
    name: 'autogenesis-container-proxy',
    configureServer(server) {
      // Registered directly (not in a returned thunk) so it runs BEFORE Vite's
      // own middlewares — including the host check, which would otherwise
      // reject these hosts before we ever see them.
      server.middlewares.use((req, res, next) => {
        const target = targetOf(req);
        if (!target) return next();
        void (async () => {
          const upstream = await resolveUpstream(gatewayPort, target);
          if (!upstream) {
            res.statusCode = 503;
            res.setHeader('content-type', 'text/plain');
            res.end(target.port
              ? `Nothing is listening on port ${target.port} in this session's container.`
              : target.service === 'science'
                ? 'The Science workstation is not running for this project.'
                : 'IDE is not running for this session.');
            return;
          }
          const { host, port, prefix } = parseUpstream(upstream);
          const proxyReq = http.request({
            host, port, method: req.method,
            path: prefix + (req.url ?? '/'),
            headers: { ...req.headers, host: `${host}:${port}` },
          }, (proxyRes) => {
            res.writeHead(proxyRes.statusCode ?? 502, proxyRes.headers);
            proxyRes.pipe(res);
          });
          proxyReq.on('error', () => {
            if (!res.headersSent) res.statusCode = 502;
            res.end(`${target.service === 'science' ? 'Science' : 'IDE'} upstream unreachable.`);
          });
          req.pipe(proxyReq);
        })();
      });

      // Both services ride a WebSocket on the same origin and path — the VS Code
      // workbench, and Jupyter's kernel channels — so the upgrade needs the same
      // routing. Vite has its own HMR upgrade listener, so only claim sockets
      // that address a container and leave the rest.
      server.httpServer?.on('upgrade', (req, socket: net.Socket, head) => {
        const target = targetOf(req);
        if (!target) return;
        void (async () => {
          const upstream = await resolveUpstream(gatewayPort, target);
          if (!upstream) { socket.destroy(); return; }
          const { host, port, prefix } = parseUpstream(upstream);
          const proxyReq = http.request({
            host, port, method: 'GET',
            path: prefix + (req.url ?? '/'),
            headers: { ...req.headers, host: `${host}:${port}` },
          });
          proxyReq.on('upgrade', (proxyRes, upstreamSocket, upstreamHead) => {
            const headers = Object.entries(proxyRes.headers)
              .map(([key, value]) => `${key}: ${Array.isArray(value) ? value.join(', ') : value}`)
              .join('\r\n');
            socket.write(`HTTP/1.1 101 Switching Protocols\r\n${headers}\r\n\r\n`);
            if (upstreamHead?.length) socket.unshift(upstreamHead);
            upstreamSocket.pipe(socket).pipe(upstreamSocket);
          });
          proxyReq.on('error', () => socket.destroy());
          if (head?.length) proxyReq.write(head);
          proxyReq.end();
        })();
      });
    },
  };
}
