import { spawn, type ChildProcessWithoutNullStreams } from 'node:child_process';
import { createInterface } from 'node:readline';
import { randomUUID } from 'node:crypto';

import type { GatewayCommand, GatewayEvent, GatewayMessage, GatewayResponse } from '../protocol.js';
import { isGatewayEvent, PROTOCOL_VERSION } from '../protocol.js';
import type { GatewayClient } from './client.js';

type PendingRequest = {
  resolve: (response: GatewayResponse) => void;
  reject: (error: Error) => void;
};

export class StdioGatewayClient implements GatewayClient {
  private child?: ChildProcessWithoutNullStreams;
  private readonly listeners = new Set<(event: GatewayEvent) => void>();
  private readonly pending = new Map<string, PendingRequest>();

  public constructor(private readonly configPath?: string, private readonly workspace = process.cwd()) {}

  public async start(): Promise<void> {
    if (this.child) return;
    const python = process.env.AUTOGENESIS_PYTHON ?? 'python';
    const args = ['-m', 'autogenesis.gateway', '--transport', 'stdio'];
    if (this.configPath) args.push('--config', this.configPath);
    this.child = spawn(python, args, { cwd: this.workspace, stdio: ['pipe', 'pipe', 'pipe'] });
    this.child.on('error', (error) => this.failPending(error));
    this.child.on('exit', (code) => {
      this.child = undefined;
      this.failPending(new Error(`Autogenesis Gateway exited (${code ?? 'unknown'})`));
      this.emitConnection('disconnected');
    });
    this.child.stderr.on('data', (data) => {
      const message = String(data).trim();
      if (message) this.emit({ kind: 'event', type: 'gateway.log', payload: { message }, seq_no: 0, timestamp: new Date().toISOString(), protocol_version: PROTOCOL_VERSION });
    });
    const lines = createInterface({ input: this.child.stdout });
    lines.on('line', (line) => this.handleLine(line));
    this.emitConnection('connected');
  }

  public async close(): Promise<void> {
    const child = this.child;
    this.child = undefined;
    if (child && !child.killed) child.kill('SIGTERM');
  }

  public request(method: string, params: Record<string, unknown> = {}): Promise<GatewayResponse> {
    if (!this.child?.stdin.writable) return Promise.reject(new Error('Local Gateway is not connected'));
    const id = randomUUID();
    const command: GatewayCommand = { id, method, params, protocol_version: PROTOCOL_VERSION };
    return new Promise<GatewayResponse>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.child?.stdin.write(`${JSON.stringify(command)}\n`, (error) => {
        if (error) {
          this.pending.delete(id);
          reject(error);
        }
      });
    });
  }

  public onEvent(listener: (event: GatewayEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private handleLine(line: string): void {
    try {
      const message = JSON.parse(line) as GatewayMessage;
      if (isGatewayEvent(message)) {
        this.emit(message);
        return;
      }
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        pending.resolve(message);
      }
    } catch {
      this.emit({ kind: 'event', type: 'gateway.log', payload: { message: line }, seq_no: 0, timestamp: new Date().toISOString(), protocol_version: PROTOCOL_VERSION });
    }
  }

  private emit(event: GatewayEvent): void {
    for (const listener of this.listeners) listener(event);
  }

  private emitConnection(status: string): void {
    this.emit({ kind: 'event', type: 'gateway.connection', payload: { status }, seq_no: 0, timestamp: new Date().toISOString(), protocol_version: PROTOCOL_VERSION });
  }

  private failPending(error: Error): void {
    for (const request of this.pending.values()) request.reject(error);
    this.pending.clear();
  }
}
