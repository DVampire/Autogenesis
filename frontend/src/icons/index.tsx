import {
  Activity,
  ArrowUpDown,
  BookOpen,
  BookOpenText,
  BookPlus,
  Bot,
  Box,
  Boxes,
  Braces,
  Cable,
  CandlestickChart,
  Code,
  Columns3,
  Combine,
  Database,
  DownloadCloud,
  FilePen,
  FilePlus2,
  FileSearch,
  FileText,
  Filter,
  Flag,
  FolderInput,
  FolderTree,
  GitBranch,
  Globe,
  KeyRound,
  LogIn,
  LogOut,
  Merge,
  MessagesSquare,
  Network,
  PenLine,
  Percent,
  Regex,
  Repeat,
  Repeat2,
  RotateCw,
  Rows3,
  Scissors,
  Search,
  ShieldCheck,
  Shuffle,
  SlidersHorizontal,
  Sparkles,
  Split,
  Table2,
  Target,
  UploadCloud,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

// Curated lucide registry the backend catalog draws NodeSpec.icon names from
// (Langflow's ForwardedIconComponent pattern — every node has its own glyph).
export const LUCIDE_ICONS: Record<string, LucideIcon> = {
  Activity, ArrowUpDown, BookOpen, BookOpenText, BookPlus, Bot, Box, Boxes, Braces, Cable, CandlestickChart, Code,
  Columns3, Combine, Database, DownloadCloud, FilePen, FilePlus2, FileSearch, FileText, Filter, Flag,
  FolderInput, FolderTree, GitBranch, Globe, KeyRound, LogIn, LogOut, Merge, MessagesSquare, Network, PenLine,
  Percent, Regex, Repeat, Repeat2, RotateCw, Rows3, Scissors, Search, ShieldCheck, Shuffle,
  SlidersHorizontal, Sparkles, Split, Table2, Target, UploadCloud, Wrench,
};

// Category → lucide icon name, used for the palette section headers.
export const CATEGORY_ICON_NAME: Record<string, string> = {
  io: 'Cable', structural: 'Split', agent: 'Sparkles', data: 'Database',
  process: 'SlidersHorizontal', evaluation: 'Target', files: 'FileText',
  knowledge: 'BookOpen', tool: 'Wrench', workflow: 'Network', plugin: 'Boxes',
};

// Each plugin's own glyph, synced from its resources/icon.svg by
// scripts/sync-plugin-icons.sh. Eagerly imported as URLs so NodeSpec.icon
// "plugin:<id>" resolves to the service's real logo (Notion, YouTube, …).
const PLUGIN_ICONS: Record<string, string> = Object.fromEntries(
  Object.entries(
    // Vite runtime API; cast keeps tsc happy without pulling in vite/client types.
    (import.meta as unknown as { glob: (p: string, o: object) => Record<string, string> })
      .glob('./plugins/*.svg', { eager: true, query: '?url', import: 'default' }),
  ).map(([path, url]) => [path.replace(/^.*\/([^/]+)\.svg$/, '$1'), url]),
);

// Meaningful lucide fallback for plugins that ship no SVG of their own, so they
// get a relevant glyph instead of an identical generic box.
const PLUGIN_LUCIDE_FALLBACK: Record<string, string> = {
  yahoo: 'CandlestickChart', fmp: 'CandlestickChart', yahoosearch: 'Search',
  mistral: 'Sparkles', baidu: 'Sparkles', ibm: 'Sparkles',
  azure: 'Sparkles', litellm: 'Sparkles',
  altk: 'Bot', cuga: 'Bot', codeagents: 'Code',
  cleanlab: 'ShieldCheck', mem0: 'BookOpen', docling: 'FileText',
  faiss: 'Database', needle: 'Database', pgvector: 'Database',
  redis: 'Database', vectara: 'Database', weaviate: 'Database',
  searchapi: 'Search', paddle: 'FileSearch', nextplaid: 'Boxes',
};

/** Resolve a node's icon: a plugin SVG ("plugin:<id>"), else a lucide
 * name, else the category glyph. */
export function NodeIcon({
  name, category, size = 16, className, strokeWidth = 2,
}: { name?: string | null; category?: string; size?: number; className?: string; strokeWidth?: number }) {
  if (name && name.startsWith('plugin:')) {
    const id = name.slice('plugin:'.length);
    const url = PLUGIN_ICONS[id];
    if (url) return <img src={url} width={size} height={size} className={className} alt="" draggable={false} style={{ objectFit: 'contain' }} />;
    // The plugin ships no SVG — a relevant lucide glyph, else a generic box.
    const Fallback = LUCIDE_ICONS[PLUGIN_LUCIDE_FALLBACK[id] ?? ''] ?? Boxes;
    return <Fallback size={size} strokeWidth={strokeWidth} className={className} />;
  }
  const Icon =
    (name && LUCIDE_ICONS[name]) ||
    (category && LUCIDE_ICONS[CATEGORY_ICON_NAME[category] ?? '']) ||
    Boxes;
  return <Icon size={size} strokeWidth={strokeWidth} className={className} />;
}

/** A palette section-header glyph (looked up by category name). */
export function CategoryGlyph({ category, size = 16, className }: { category: string; size?: number; className?: string }) {
  return <NodeIcon name={CATEGORY_ICON_NAME[category]} category={category} size={size} className={className} />;
}
