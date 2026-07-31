import { memo } from 'react';
import { BaseEdge, getBezierPath, useStore, type EdgeProps } from '@xyflow/react';

import { PORT_COLORS, type CanvasData, type PortType } from '../canvas/types';

// Mirror OutputPorts' coloring so an edge matches the dot it leaves from.
const IO_INPUT_PORT: Record<string, PortType> = { string: 'text', array: 'list', object: 'object', number: 'text', boolean: 'text' };
function sourceOutputType(data?: CanvasData): PortType {
  if (!data) return 'any';
  if (data.type === 'input') return IO_INPUT_PORT[data.io?.input_type] ?? 'any';
  const spec = data.spec;
  return (spec?.outputs?.length ?? 0) > 1 ? 'any' : (spec?.outputs?.[0]?.type ?? 'any');
}

/** Default bezier edge, ported (simplified) from langflow's
 * CustomEdges/DefaultEdge: BaseEdge over getBezierPath, stroked in the source
 * handle's datatype color (Langflow colors edges by type) except when selected,
 * where the selection highlight takes over. */
export const DefaultEdge = memo(function DefaultEdge({
  source, sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition, selected, markerEnd, style,
}: EdgeProps) {
  const [path] = getBezierPath({ sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition });
  const type = useStore((state) => sourceOutputType(state.nodeLookup.get(source)?.data as CanvasData | undefined));
  const color = PORT_COLORS[type] ?? PORT_COLORS.any;
  return (
    <BaseEdge
      path={path}
      markerEnd={markerEnd}
      className={`lf-edge${selected ? ' selected' : ''}`}
      style={{ ...style, ...(selected ? {} : { stroke: color }) }}
    />
  );
});

export const EDGE_TYPES = { default: DefaultEdge };
