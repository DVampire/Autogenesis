import { Box, Text } from 'ink';

import type { ConnectionState } from '../state.js';

const colors: Record<ConnectionState, string> = {
  connecting: 'yellow',
  connected: 'green',
  disconnected: 'red',
  error: 'red',
};

export function Header({ connection, sessionId, remote }: { connection: ConnectionState; sessionId?: string; remote: boolean }) {
  return (
    <Box justifyContent="space-between" paddingX={1} borderStyle="round" borderColor="cyan">
      <Text bold color="cyan">Autogenesis</Text>
      <Text color={colors[connection]}>{connection}</Text>
      <Text dimColor>{remote ? 'WebSocket' : 'local'} · {sessionId ? sessionId.slice(0, 8) : 'starting'}</Text>
    </Box>
  );
}
