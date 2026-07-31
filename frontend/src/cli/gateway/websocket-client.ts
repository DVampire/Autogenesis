import { randomUUID } from 'node:crypto';
import WebSocket from 'ws';

import type { GatewayCommand, GatewayEvent, GatewayMessage, GatewayResponse } from '../protocol.js';
import { isGatewayEvent, PROTOCOL_VERSION } from '../protocol.js';
import type { GatewayClient } from './client.js';

type PendingRequest = {
  resolve: (response: GatewayResponse) => void;
  reject: (error: Error) => void;
};

export class WebSocketGatewayClient implements GatewayClient {
  private socket?: WebSocket;
  private readonly listeners = new Set<(event: GatewayEvent) => void>();
  private readonly pending = new Map<string, PendingRequest>();
  private readonly lastSequenceBySession = new Map<string, number>();
  private shouldReconnect = true;
  private reconnectTimer?: NodeJS.Timeout;
  private reconnectAttempt = 0;

  public constructor(private readonly url: string, private readonly token?: string) {}

  public async start(): Promise<void> {
    this.shouldReconnect = true;
    await this.connect();
  }

  public async close(): Promise<void> {
    this.shouldReconnect = false;
    if (this.reconnectTimer) clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = undefined;
    this.failPending(new Error('Gateway connection closed'));
  }

  public request(method: string, params: Record<string, unknown> = {}): Promise<GatewayResponse> {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Remote Gateway is not connected'));
    }
    const id = randomUUID();
    const command: GatewayCommand = { id, method, params, protocol_version: PROTOCOL_VERSION };
    return new Promise<GatewayResponse>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket?.send(JSON.stringify(command), (error) => {
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

  private connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const url = this.token ? this.withToken(this.url, this.token) : this.url;
      const socket = new WebSocket(url, this.token ? { headers: { Authorization: `Bearer ${this.token}` } } : undefined);
      this.socket = socket;
      let opened = false;
      socket.once('open', async () => {
        opened = true;
        this.reconnectAttempt = 0;
        this.emitConnection('connected');
        await this.replayMissedEvents();
        resolve();
      });
      socket.on('message', (data) => this.handleMessage(String(data)));
      socket.once('error', (error) => {
        if (!opened) reject(error);
      });
      socket.on('close', () => {
        this.emitConnection('disconnected');
        this.failPending(new Error('Gateway connection closed'));
        if (this.shouldReconnect) this.scheduleReconnect();
      });
    });
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(1_000 * 2 ** this.reconnectAttempt, 15_000);
    this.reconnectAttempt += 1;
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = undefined;
      void this.connect().catch(() => undefined);
    }, delay);
  }

  private async replayMissedEvents(): Promise<void> {
    for (const [sessionId, afterSeq] of this.lastSequenceBySession) {
      const response = await this.request('session.events', { session_id: sessionId, after_seq: afterSeq });
      const events = response.result.events;
      if (Array.isArray(events)) {
        for (const event of events as GatewayEvent[]) this.handleEvent(event);
      }
    }
  }

  private handleMessage(raw: string): void {
    try {
      const message = JSON.parse(raw) as GatewayMessage;
      if (isGatewayEvent(message)) {
        this.handleEvent(message);
        return;
      }
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        pending.resolve(message);
      }
    } catch {
      this.emit({ kind: 'event', type: 'gateway.log', payload: { message: raw }, seq_no: 0, timestamp: new Date().toISOString(), protocol_version: PROTOCOL_VERSION });
    }
  }

  private handleEvent(event: GatewayEvent): void {
    if (event.session_id && event.seq_no > 0) this.lastSequenceBySession.set(event.session_id, event.seq_no);
    this.emit(event);
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

  private withToken(rawUrl: string, token: string): string {
    const url = new URL(rawUrl);
    url.searchParams.set('token', token);
    return url.toString();
  }
}
