import type { GatewayClient, GatewayClientOptions } from './client.js';
import { StdioGatewayClient } from './stdio-client.js';
import { WebSocketGatewayClient } from './websocket-client.js';

export type { GatewayClient, GatewayClientOptions } from './client.js';

export function createGatewayClient(options: GatewayClientOptions): GatewayClient {
  return options.connectUrl
    ? new WebSocketGatewayClient(options.connectUrl, options.token)
    : new StdioGatewayClient(options.configPath, options.workspace);
}
