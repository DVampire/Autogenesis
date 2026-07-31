import { useCallback, useRef } from 'react';
import type { Edge } from '@xyflow/react';

import { MAX_HISTORY_SIZE } from '../constants/constants';
import type { CanvasNode } from './types';

interface Snapshot { nodes: CanvasNode[]; edges: Edge[]; }

function clone(snapshot: Snapshot): Snapshot {
  // Node data holds functions (update) and Sets; structuredClone would drop
  // them, so copy graph structure shallowly and data by reference-safe spread.
  return {
    nodes: snapshot.nodes.map((node) => ({ ...node, data: { ...node.data, boundParams: new Set(node.data.boundParams), args: { ...node.data.args }, attrs: { ...node.data.attrs }, io: { ...node.data.io } }, position: { ...node.position } })),
    edges: snapshot.edges.map((edge) => ({ ...edge })),
  };
}

function same(left: Snapshot, right: Snapshot): boolean {
  const strip = (snapshot: Snapshot) => JSON.stringify({
    nodes: snapshot.nodes.map((node) => ({ id: node.id, parentId: node.parentId, position: node.position, task: node.data.task, args: node.data.args, attrs: node.data.attrs, items: node.data.items, io: node.data.io, target: node.data.target })),
    edges: snapshot.edges.map((edge) => ({ id: edge.id, source: edge.source, target: edge.target, targetHandle: edge.targetHandle })),
  });
  return strip(left) === strip(right);
}

/** Snapshot-based history, ported from Langflow's flowsManagerStore
 * (takeSnapshot / undo / redo with dedupe and a bounded past). */
export function useUndoRedo(
  getCurrent: () => Snapshot,
  restore: (snapshot: Snapshot) => void,
) {
  const past = useRef<Snapshot[]>([]);
  const future = useRef<Snapshot[]>([]);

  const takeSnapshot = useCallback(() => {
    const current = clone(getCurrent());
    const last = past.current[past.current.length - 1];
    if (last && same(last, current)) return;
    past.current = [...past.current.slice(-(MAX_HISTORY_SIZE - 1)), current];
    future.current = [];
  }, [getCurrent]);

  const undo = useCallback(() => {
    const previous = past.current.pop();
    if (!previous) return;
    const current = clone(getCurrent());
    if (same(previous, current)) {
      // The top snapshot equals the live state (snapshot was taken right
      // before an aborted change): step one further back, Langflow-style.
      const older = past.current.pop();
      if (!older) { past.current.push(previous); return; }
      future.current.push(current);
      restore(older);
      return;
    }
    future.current.push(current);
    restore(previous);
  }, [getCurrent, restore]);

  const redo = useCallback(() => {
    const next = future.current.pop();
    if (!next) return;
    past.current.push(clone(getCurrent()));
    restore(next);
  }, [getCurrent, restore]);

  const reset = useCallback(() => { past.current = []; future.current = []; }, []);

  return { takeSnapshot, undo, redo, reset };
}
