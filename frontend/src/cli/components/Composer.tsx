import { Box, Text } from 'ink';

export function Composer({ value, disabled }: { value: string; disabled: boolean }) {
  return (
    <Box borderStyle="round" borderColor={disabled ? 'gray' : 'green'} paddingX={1}>
      <Text color="green">› </Text>
      <Text>{value || <Text dimColor>{disabled ? 'Connecting to Gateway…' : 'Describe a task; Ctrl+C cancels'}</Text>}</Text>
    </Box>
  );
}
