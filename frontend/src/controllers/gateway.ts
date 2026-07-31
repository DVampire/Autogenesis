export const PROTOCOL_VERSION = 1;

export interface GatewayResponse {
  kind: 'response';
  id: string;
  ok: boolean;
  result: Record<string, unknown>;
  error?: { code: string; message: string };
}

export interface GatewayEvent {
  kind: 'event';
  type: string;
  payload: Record<string, unknown>;
  session_id?: string;
  // Which transcript this belongs to. The gateway broadcasts every event to
  // every client, so a view that owns one conversation has to filter on it —
  // without this, a canvas run appeared in the chat.
  conversation_id?: string;
  task_id?: string;
  seq_no: number;
  timestamp: string;
}

type PendingRequest = {
  resolve: (response: GatewayResponse) => void;
  reject: (error: Error) => void;
};

export class GatewaySocket {
  private socket?: WebSocket;
  private readonly listeners = new Set<(event: GatewayEvent) => void>();
  private readonly statusListeners = new Set<(status: ConnectionStatus) => void>();
  private readonly pending = new Map<string, PendingRequest>();
  private readonly lastSequence = new Map<string, number>();
  private reconnectTimer?: number;
  private reconnectAttempts = 0;
  private shouldReconnect = true;

  public constructor(private readonly endpoint: string, private readonly token?: string) {}

  public connect(): void {
    this.shouldReconnect = true;
    this.open();
  }

  public close(): void {
    this.shouldReconnect = false;
    window.clearTimeout(this.reconnectTimer);
    this.socket?.close();
    this.socket = undefined;
    this.rejectPending(new Error('Gateway connection closed'));
  }

  public onEvent(listener: (event: GatewayEvent) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  public onStatus(listener: (status: ConnectionStatus) => void): () => void {
    this.statusListeners.add(listener);
    return () => this.statusListeners.delete(listener);
  }

  public forgetSession(sessionId: string): void {
    this.lastSequence.delete(sessionId);
  }

  public request(method: string, params: Record<string, unknown> = {}): Promise<GatewayResponse> {
    if (!this.socket || this.socket.readyState !== WebSocket.OPEN) {
      return Promise.reject(new Error('Gateway is not connected'));
    }
    const id = crypto.randomUUID();
    const payload = { id, method, params, protocol_version: PROTOCOL_VERSION };
    return new Promise<GatewayResponse>((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.socket?.send(JSON.stringify(payload));
    });
  }

  private open(): void {
    this.setStatus('connecting');
    this.socket = new WebSocket(this.withToken());
    this.socket.onopen = async () => {
      this.reconnectAttempts = 0;
      this.setStatus('connected');
      try {
        await this.replayMissedEvents();
      } catch {
        // A restarted Gateway can no longer replay an old ephemeral session.
      }
    };
    this.socket.onmessage = (message) => this.handleMessage(message.data);
    this.socket.onerror = () => this.setStatus('error');
    this.socket.onclose = () => {
      this.setStatus('disconnected');
      this.rejectPending(new Error('Gateway connection closed'));
      if (this.shouldReconnect) this.scheduleReconnect();
    };
  }

  private handleMessage(raw: unknown): void {
    try {
      const message = JSON.parse(String(raw)) as GatewayEvent | GatewayResponse;
      if (message.kind === 'event') {
        if (message.session_id && message.seq_no > 0) this.lastSequence.set(message.session_id, message.seq_no);
        for (const listener of this.listeners) listener(message);
        return;
      }
      const pending = this.pending.get(message.id);
      if (pending) {
        this.pending.delete(message.id);
        pending.resolve(message);
      }
    } catch {
      // Ignore malformed transport data; the next well-formed event restores state.
    }
  }

  private async replayMissedEvents(): Promise<void> {
    for (const [sessionId, afterSeq] of this.lastSequence) {
      const response = await this.request('session.events', { session_id: sessionId, after_seq: afterSeq });
      const events = response.result.events;
      if (Array.isArray(events)) {
        for (const event of events as GatewayEvent[]) {
          for (const listener of this.listeners) listener(event);
        }
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.reconnectTimer) return;
    const delay = Math.min(1_000 * 2 ** this.reconnectAttempts, 15_000);
    this.reconnectAttempts += 1;
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = undefined;
      this.open();
    }, delay);
  }

  private setStatus(status: ConnectionStatus): void {
    for (const listener of this.statusListeners) listener(status);
  }

  private rejectPending(error: Error): void {
    for (const pending of this.pending.values()) pending.reject(error);
    this.pending.clear();
  }

  private withToken(): string {
    if (!this.token) return this.endpoint;
    const url = new URL(this.endpoint);
    url.searchParams.set('token', this.token);
    return url.toString();
  }
}

export type ConnectionStatus = 'connecting' | 'connected' | 'disconnected' | 'error';
