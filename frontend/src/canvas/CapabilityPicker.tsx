import { createContext, useContext, useMemo, useState } from 'react';
import { ChevronDown, Search, X } from 'lucide-react';

import { Popover, PopoverContent, PopoverTrigger } from '../components/ui/popover';
import { MOUNT_LABELS, type MountRosters } from './types';

/** Global capability rosters (from canvas.catalog) shared with every agent node. */
export const MountRosterContext = createContext<MountRosters>({});

/** The inline control for one agent mount type (Tools / Skills / Connectors /
 * Workflows / Environments / Agents). Rendered as the body of a FieldShell (the
 * shell supplies the wire handle + label). Click the box to multi-select from
 * the roster; selected items show as chips. Empty = the agent's defaults. Wiring
 * a node into the handle also grants access, so an edge takes precedence. */
export function MountPicker({ type, label, selected, connected, onChange }: {
  type: string; label: string; selected: string[]; connected: boolean; onChange: (next: string[]) => void;
}) {
  const rosters = useContext(MountRosterContext);
  const roster = rosters[type] ?? [];
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const nice = MOUNT_LABELS[type] ?? label;

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    return roster.filter((item) => !q || item.name.toLowerCase().includes(q) || item.description.toLowerCase().includes(q));
  }, [roster, query]);

  const toggle = (name: string) =>
    onChange(selected.includes(name) ? selected.filter((item) => item !== name) : [...selected, name]);

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className="lf-mount-box nodrag" title={`Pick ${nice.toLowerCase()} for this agent`}>
          <span className="lf-mount-box-body">
            {connected ? (
              <span className="lf-bound">Connected</span>
            ) : selected.length ? (
              selected.map((name) => (
                <span className="lf-chip" key={name}>
                  {name}
                  <button aria-label={`Remove ${name}`}
                    onClick={(event) => { event.stopPropagation(); toggle(name); }}><X size={11} /></button>
                </span>
              ))
            ) : (
              <span className="lf-mount-placeholder">Wire nodes, or click to pick</span>
            )}
          </span>
          <ChevronDown size={13} className="lf-mount-caret" />
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-64 p-0 nodrag nowheel" align="start">
        {roster.length ? (
          <>
            <div className="flex items-center gap-2 border-b border-border px-2.5 py-2">
              <Search size={13} className="text-muted-foreground" />
              <input autoFocus value={query} onChange={(event) => setQuery(event.target.value)}
                placeholder={`Search ${nice.toLowerCase()}…`} className="w-full bg-transparent text-xs outline-none" />
            </div>
            <div className="max-h-56 overflow-y-auto py-1">
              {filtered.map((item) => (
                <button key={item.name} onClick={() => toggle(item.name)}
                  className={`flex w-full items-start gap-2 px-2.5 py-1.5 text-left text-xs hover:bg-muted ${selected.includes(item.name) ? 'text-foreground' : 'text-muted-foreground'}`}>
                  <span className={`mt-0.5 grid h-3.5 w-3.5 flex-none place-items-center rounded border ${selected.includes(item.name) ? 'border-primary bg-primary text-primary-foreground' : 'border-border'}`}>
                    {selected.includes(item.name) ? '✓' : ''}
                  </span>
                  <span className="min-w-0"><strong className="block truncate font-medium text-foreground">{item.name}</strong>{item.description ? <span className="block truncate">{item.description}</span> : null}</span>
                </button>
              ))}
              {!filtered.length ? <p className="px-2.5 py-3 text-center text-xs text-muted-foreground">No match.</p> : null}
            </div>
          </>
        ) : (
          <p className="px-2.5 py-3 text-center text-xs text-muted-foreground">No {nice.toLowerCase()} available.</p>
        )}
      </PopoverContent>
    </Popover>
  );
}
