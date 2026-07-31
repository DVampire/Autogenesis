import { useMemo, useState } from 'react';
import { Boxes, ChevronRight, GripVertical, PanelLeft, PanelLeftClose, Plus, Search } from 'lucide-react';

import ShadTooltip from '../components/common/shadTooltipComponent';
import { Input } from '../components/ui/input';
import { useDebounce } from '../hooks/use-debounce';
import { CategoryGlyph, NodeIcon } from '../icons';
import { CATEGORY_LABELS, CATEGORY_ORDER, DND_MIME, type NodeSpec } from './types';

/** One draggable palette row (double-click / + button also places the node).
 * Markup copied verbatim from Langflow's sidebarDraggableComponent. */
function DraggableRow({ spec, onAdd }: { spec: NodeSpec; onAdd: (spec: NodeSpec) => void }) {
  return (
    <div title={spec.description} className="my-1 rounded-md outline-none ring-ring focus-visible:ring-1" tabIndex={0}>
      <div
        className="group/draggable flex cursor-grab items-center gap-2 rounded-md bg-muted p-1 px-2 text-foreground hover:bg-secondary-hover/75"
        draggable
        onDragStart={(event) => { event.dataTransfer.setData(DND_MIME, spec.id); event.dataTransfer.effectAllowed = 'copy'; }}
        onDoubleClick={() => onAdd(spec)}>
        <NodeIcon name={spec.icon} category={spec.category} size={18} className="h-[18px] w-[18px] shrink-0" />
        <div className="flex flex-1 items-center overflow-hidden">
          <span className="truncate text-sm font-normal">{spec.label}</span>
        </div>
        <div className="flex shrink-0 items-center gap-1">
          <button tabIndex={-1} className="text-primary opacity-0 transition-all group-hover/draggable:opacity-100" onClick={() => onAdd(spec)} aria-label={`Add ${spec.label}`}>
            <Plus className="h-4 w-4 shrink-0" />
          </button>
          <GripVertical className="h-4 w-4 shrink-0 text-muted-foreground group-hover/draggable:text-primary" />
        </div>
      </div>
    </div>
  );
}

/** Langflow-style component sidebar: search, collapsible category sections,
 * draggable rows (double-click also places the node). Collapses to a thin icon
 * rail (Langflow's sidebarSegmentedNav) to give the canvas more room. */
export function Palette({ specs, connected, onAdd }: { specs: NodeSpec[]; connected: boolean; onAdd: (spec: NodeSpec) => void }) {
  const [search, setSearch] = useState('');
  const [railed, setRailed] = useState(false);
  const [collapsed, setCollapsed] = useState<Set<string>>(() => new Set(['agent', 'workflow']));
  // The Plugins super-section and each plugin sub-group start collapsed: there
  // are 88 plugins, and expanded by default they would bury everything else.
  const [pluginsOpen, setPluginsOpen] = useState(false);
  const [openPlugins, setOpenPlugins] = useState<Set<string>>(() => new Set());
  const query = useDebounce(search, 150).trim().toLowerCase();

  // Categories that actually have components — for the collapsed icon rail.
  const railCategories = useMemo(
    () => CATEGORY_ORDER.filter((category) => specs.some((spec) => spec.category === category)),
    [specs],
  );

  const matches = (spec: NodeSpec) =>
    !query || spec.label.toLowerCase().includes(query) || spec.id.toLowerCase().includes(query)
    || (spec.plugin_label ?? '').toLowerCase().includes(query);

  // Normal (non-plugin) categories.
  const grouped = useMemo(() => {
    const filtered = specs.filter((spec) => spec.category !== 'plugin' && matches(spec));
    return CATEGORY_ORDER.map((category) => ({ category, items: filtered.filter((spec) => spec.category === category) })).filter((group) => group.items.length);
  }, [specs, query]);

  // Plugin tools: category === 'plugin', nested one level deeper (plugin → its
  // tools). Sorted by plugin label; a search matches the plugin name too, so
  // typing "notion" reveals the whole Notion group.
  const pluginGroups = useMemo(() => {
    const byPlugin = new Map<string, { label: string; icon: string; items: NodeSpec[] }>();
    for (const spec of specs) {
      if (spec.category !== 'plugin' || !spec.plugin) continue;
      const pluginMatch = !query || (spec.plugin_label ?? spec.plugin).toLowerCase().includes(query);
      if (!pluginMatch && !matches(spec)) continue;
      const group = byPlugin.get(spec.plugin) ?? { label: spec.plugin_label || spec.plugin, icon: spec.icon || `plugin:${spec.plugin}`, items: [] };
      group.items.push(spec);
      byPlugin.set(spec.plugin, group);
    }
    return [...byPlugin.entries()]
      .map(([id, g]) => ({ id, ...g }))
      .sort((a, b) => a.label.localeCompare(b.label));
  }, [specs, query]);

  // Collapsed icon rail. Returned here — after every hook above has run — so
  // toggling `railed` never changes the hook count (Rules of Hooks).
  if (railed) {
    return (
      <aside className="canvas-catalog collapsed">
        <div className="lf-rail">
          <ShadTooltip content="Expand components" side="right">
            <button className="lf-rail-btn" onClick={() => setRailed(false)} aria-label="Expand components"><PanelLeft className="h-5 w-5" /></button>
          </ShadTooltip>
          <div className="lf-rail-sep" />
          {railCategories.map((category) => (
            <ShadTooltip key={category} content={CATEGORY_LABELS[category]} side="right">
              <button
                className="lf-rail-btn"
                onClick={() => { setRailed(false); setCollapsed((current) => { const next = new Set(current); next.delete(category); return next; }); }}
                aria-label={CATEGORY_LABELS[category]}
              >
                <CategoryGlyph category={category} size={18} />
              </button>
            </ShadTooltip>
          ))}
        </div>
      </aside>
    );
  }

  const toggle = (category: string) => setCollapsed((current) => {
    const next = new Set(current);
    next.has(category) ? next.delete(category) : next.add(category);
    return next;
  });
  const togglePlugin = (id: string) => setOpenPlugins((current) => {
    const next = new Set(current);
    next.has(id) ? next.delete(id) : next.add(id);
    return next;
  });

  return (
    <aside className="canvas-catalog">
      <div className="relative mx-3 mb-2.5 mt-3.5">
        <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
        <Input className="h-9 pl-9 text-sm" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search" />
      </div>
      <div className="canvas-catalog-head">
        <p className="canvas-catalog-title">Components</p>
        <ShadTooltip content="Collapse" side="right">
          <button className="lf-rail-btn ml-auto" onClick={() => setRailed(true)} aria-label="Collapse components"><PanelLeftClose className="h-4 w-4" /></button>
        </ShadTooltip>
      </div>
      <div className="canvas-catalog-list">
        {grouped.map((group) => {
          const isCollapsed = collapsed.has(group.category) && !query;
          return (
            <section key={group.category}>
              <button className="canvas-cat-head" onClick={() => toggle(group.category)} aria-expanded={!isCollapsed}>
                <CategoryGlyph category={group.category} className="lf-cat-icon" />
                <strong>{CATEGORY_LABELS[group.category]}</strong>
                <span className="lf-cat-count">{group.items.length}</span>
                <em className="lf-cat-chevron"><ChevronRight size={14} /></em>
              </button>
              {!isCollapsed ? group.items.map((spec) => (
                <DraggableRow key={spec.id} spec={spec} onAdd={onAdd} />
              )) : null}
            </section>
          );
        })}

        {/* Plugins — one sub-group per service, its tools nested inside. */}
        {pluginGroups.length ? (
          <section className="lf-plugins">
            <button className="canvas-cat-head" onClick={() => setPluginsOpen((open) => !open)} aria-expanded={pluginsOpen || !!query}>
              <Boxes className="lf-cat-icon" size={16} />
              <strong>Plugins</strong>
              <span className="lf-cat-count">{pluginGroups.length}</span>
              <em className="lf-cat-chevron"><ChevronRight size={14} /></em>
            </button>
            {(pluginsOpen || query) ? pluginGroups.map((plugin) => {
              const open = openPlugins.has(plugin.id) || !!query;
              return (
                <div key={plugin.id} className="lf-plugin">
                  <button className="canvas-cat-head lf-plugin-head" onClick={() => togglePlugin(plugin.id)} aria-expanded={open}>
                    <NodeIcon name={plugin.icon} category="plugin" size={16} className="lf-cat-icon" />
                    <strong>{plugin.label}</strong>
                    <span className="lf-cat-count">{plugin.items.length}</span>
                    <em className="lf-cat-chevron"><ChevronRight size={13} /></em>
                  </button>
                  {open ? plugin.items.map((spec) => (
                    <DraggableRow key={spec.id} spec={spec} onAdd={onAdd} />
                  )) : null}
                </div>
              );
            }) : null}
          </section>
        ) : null}

        {!grouped.length && !pluginGroups.length ? <p className="empty">{connected ? 'No components match this search.' : 'Connecting…'}</p> : null}
      </div>
    </aside>
  );
}
