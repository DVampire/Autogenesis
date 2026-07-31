import { Box, Text } from 'ink';

export function StatusBar({ taskId, notice }: { taskId?: string; notice?: string }) {
  return (
    <Box justifyContent="space-between" paddingX={1}>
      <Text dimColor>{taskId ? `running ${taskId.slice(0, 8)}` : 'idle'}</Text>
      <Text dimColor>{notice ?? 'Enter submit · Ctrl+C cancel/exit · q quit'}</Text>
    </Box>
  );
}
