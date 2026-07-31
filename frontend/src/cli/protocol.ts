export const PROTOCOL_VERSION = 1;

export interface GatewayCommand {
  id: string;
  method: string;
  params: Record<string, unknown>;
  protocol_version: number;
}

export interface GatewayError {
  code: string;
  message: string;
  details?: Record<string, unknown>;
}

export interface GatewayResponse {
  kind: 'response';
  id: string;
  ok: boolean;
  result: Record<string, unknown>;
  error?: GatewayError;
  protocol_version: number;
}

export interface GatewayEvent {
  kind: 'event';
  type: string;
  payload: Record<string, unknown>;
  session_id?: string;
  task_id?: string;
  seq_no: number;
  timestamp: string;
  protocol_version: number;
}

export type GatewayMessage = GatewayEvent | GatewayResponse;

export function isGatewayEvent(message: GatewayMessage): message is GatewayEvent {
  return message.kind === 'event';
}
