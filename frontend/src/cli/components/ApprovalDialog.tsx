import { Box, Text } from 'ink';

import type { ApprovalState } from '../state.js';

export function ApprovalDialog({ approval }: { approval: ApprovalState }) {
  return (
    <Box borderStyle="double" borderColor="yellow" flexDirection="column" paddingX={1}>
      <Text bold color="yellow">Approval required</Text>
      <Text>{approval.summary}</Text>
      <Text dimColor>[a] allow once   [r] reject</Text>
    </Box>
  );
}
