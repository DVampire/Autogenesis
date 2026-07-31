import { Box, Text } from 'ink';

import type { TimelineEntry } from '../state.js';

const colors = { user: 'cyan', agent: 'green', tool: 'yellow', system: 'gray', error: 'red' } as const;

export function Transcript({ entries }: { entries: TimelineEntry[] }) {
  if (!entries.length) {
    return <Box paddingX={1} paddingY={1}><Text dimColor>Describe a task to start an Autogenesis session.</Text></Box>;
  }
  return (
    <Box flexDirection="column" paddingX={1}>
      {entries.slice(-80).map((entry) => (
        <Box key={entry.id} flexDirection="column" marginBottom={1}>
          <Text color={colors[entry.type]} bold>{entry.pending ? '◌ ' : '• '}{entry.title}</Text>
          {entry.body ? <Text wrap="wrap">{truncate(entry.body, 1_500)}</Text> : null}
        </Box>
      ))}
    </Box>
  );
}

function truncate(value: string, maxLength: number): string {
  return value.length > maxLength ? `${value.slice(0, maxLength)}…` : value;
}
