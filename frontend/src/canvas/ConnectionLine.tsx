import type { ConnectionLineComponentProps } from '@xyflow/react';

import { PORT_COLORS, type CanvasData, type NodeSpec, type PortType } from './types';

// Resolve the datatype of the handle a connection is being dragged from, so the
// line + end dot can be colored by type — mirroring Langflow's
// ConnectionLineComponent (`hsl(var(--datatype-${handleDragging.color}))`).
function draggedPortType(spec: NodeSpec | undefined, handle: { id?: string | null; type?: string | null } | null | undefined): PortType {
  if (!handle) return 'any';
  if (handle.type === 'source') {
    return (spec?.outputs?.length ?? 0) > 1 ? 'any' : (spec?.outputs?.[0]?.type ?? 'any');
  }
  return spec?.inputs?.find((port) => port.name === handle.id)?.type ?? 'any';
}

/** In-progress connection line, ported from Langflow's
 * ConnectionLineComponent: an animated cubic path ending in a ringed dot,
 * stroked in the dragged handle's datatype color. */
export default function ConnectionLine({ fromX, fromY, toX, toY, fromNode, fromHandle, connectionLineStyle = {} }: ConnectionLineComponentProps) {
  const spec = (fromNode?.data as CanvasData | undefined)?.spec;
  const type = draggedPortType(spec, fromHandle);
  const color = PORT_COLORS[type] ?? PORT_COLORS.any;
  return (
    <g>
      <path
        fill="none"
        strokeWidth={2}
        className="canvas-connection-line"
        style={{ stroke: color, ...connectionLineStyle }}
        d={`M${fromX},${fromY} C ${fromX} ${toY} ${fromX} ${toY} ${toX},${toY}`}
      />
      <circle cx={toX} cy={toY} r={5} strokeWidth={1.5} fill="hsl(var(--background))" style={{ stroke: color }} className="canvas-connection-dot" />
    </g>
  );
}
