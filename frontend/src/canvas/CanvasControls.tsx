import { Panel, useReactFlow, useStore } from '@xyflow/react';
import { ChevronUp, HelpCircle, Minimize2, StickyNote } from 'lucide-react';

import ShadTooltip from '../components/common/shadTooltipComponent';
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel,
  DropdownMenuSeparator, DropdownMenuShortcut, DropdownMenuTrigger,
} from '../components/ui/dropdown-menu';

// Bottom-center controls pill copied from Langflow's CanvasControls: a fixed
// (screen-space, never scales with the canvas) rounded bar with a zoom-%
// dropdown (in/out/100%/fit all live inside — no inline +/- buttons), add
// sticky note, minimize-all, and a help dropdown.
const ZOOM = { duration: 250 } as const;

function BarButton({ icon: Icon, label, active, onClick }: { icon: typeof StickyNote; label: string; active?: boolean; onClick: () => void }) {
  return (
    <ShadTooltip content={label}>
      <button
        type="button"
        aria-label={label}
        onClick={onClick}
        className={`group flex h-8 w-8 items-center justify-center rounded-md ${active ? 'bg-muted text-foreground' : 'hover:bg-muted'}`}
      >
        <Icon className={`h-[18px] w-[18px] transition-colors ${active ? 'text-foreground' : 'text-muted-foreground group-hover:text-foreground'}`} />
      </button>
    </ShadTooltip>
  );
}

export function CanvasControls() {
  const { zoomIn, zoomOut, fitView, zoomTo } = useReactFlow();
  const zoom = useStore((state) => state.transform[2]);
  return (
    <Panel
      position="bottom-center"
      data-testid="main_canvas_controls"
      className="react-flow__controls !m-4 flex !flex-row items-center gap-1 !overflow-visible rounded-lg border border-border bg-background p-1 text-primary shadow-md [&>button]:border-0"
    >
      {/* Zoom % dropdown — Langflow CanvasControlsDropdown */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            title="Zoom"
            data-testid="canvas_controls_dropdown"
            className="group flex h-8 items-center justify-center gap-1 rounded-md px-0.5 hover:bg-muted"
          >
            <span className="w-11 pl-1.5 text-left text-sm tabular-nums text-muted-foreground group-hover:text-foreground">{Math.round(zoom * 100)}%</span>
            <ChevronUp className="h-5 w-5 text-muted-foreground group-hover:text-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="center" className="w-44">
          <DropdownMenuItem onClick={() => zoomIn(ZOOM)}>Zoom in<DropdownMenuShortcut>+</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem onClick={() => zoomOut(ZOOM)}>Zoom out<DropdownMenuShortcut>−</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onClick={() => zoomTo(1, ZOOM)}>Zoom to 100%<DropdownMenuShortcut>0</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem onClick={() => fitView(ZOOM)}>Fit view<DropdownMenuShortcut>1</DropdownMenuShortcut></DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <BarButton icon={StickyNote} label="Add sticky note" onClick={() => window.dispatchEvent(new Event('canvas-add-note'))} />
      <BarButton icon={Minimize2} label="Minimize all nodes" onClick={() => window.dispatchEvent(new Event('canvas-minimize-all'))} />

      {/* Help — keyboard shortcuts (Langflow HelpDropdown) */}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label="Help" className="group flex h-8 w-8 items-center justify-center rounded-md hover:bg-muted">
            <HelpCircle className="h-[18px] w-[18px] text-muted-foreground transition-colors group-hover:text-foreground" />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent side="top" align="center" className="w-52">
          <DropdownMenuLabel>Keyboard shortcuts</DropdownMenuLabel>
          <DropdownMenuSeparator />
          <DropdownMenuItem>Undo<DropdownMenuShortcut>⌘Z</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem>Redo<DropdownMenuShortcut>⌘⇧Z</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem>Copy<DropdownMenuShortcut>⌘C</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem>Paste<DropdownMenuShortcut>⌘V</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem>Duplicate<DropdownMenuShortcut>⌘D</DropdownMenuShortcut></DropdownMenuItem>
          <DropdownMenuItem>Delete<DropdownMenuShortcut>⌫</DropdownMenuShortcut></DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </Panel>
  );
}
