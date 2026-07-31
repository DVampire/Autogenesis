import type { GatewayEvent, GatewayResponse } from '../protocol.js';

export interface GatewayClient {
  start(): Promise<void>;
  close(): Promise<void>;
  request(method: string, params?: Record<string, unknown>): Promise<GatewayResponse>;
  onEvent(listener: (event: GatewayEvent) => void): () => void;
}

export interface GatewayClientOptions {
  configPath?: string;
  connectUrl?: string;
  token?: string;
  workspace?: string;
}
