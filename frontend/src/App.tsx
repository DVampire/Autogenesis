import { isValidElement, lazy, Suspense, type FormEvent, type KeyboardEvent, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { CodeBlock, MARKDOWN_REHYPE_PLUGINS, MessageMarkdown, reactNodeText } from './components/common/Markdown';
import {
  Boxes,
  Cable,
  GraduationCap,
  MessageSquare,
  Monitor,
  Moon,
  Plus,
  RefreshCw,
  Settings,
  Sparkles,
  Code2,
  FlaskConical,
  PanelLeftClose,
  PanelLeftOpen,
  SquareTerminal,
  Sun,
  Waypoints,
  Workflow,
  Wrench,
  type LucideIcon,
} from 'lucide-react';

import AlertDisplayArea from './alerts';
import { TooltipProvider } from './components/ui/tooltip';
import { type ConnectionStatus, type GatewayEvent, GatewaySocket } from './controllers/gateway';
import useAlertStore from './stores/alertStore';

type CapabilityKind = 'agents' | 'tools' | 'skills' | 'connectors' | 'environments' | 'workflows' | 'commands' | 'canvas';
type MessageType = 'user' | 'assistant' | 'system' | 'error';
type ActivityStatus = 'running' | 'completed' | 'failed' | 'cancelled';
type Theme = 'dark' | 'light';

// One available capability, tagged with where it came from (default vs the
// shared extension root) and whether it self-evolves.
interface CapabilityItem { type: string; name: string; source: 'default' | 'extension'; evolving: boolean; }
type CapabilityCatalog = Record<CapabilityKind, CapabilityItem[]>;
// The session's selected capabilities are tracked by name only.
type CapabilitySelection = Record<CapabilityKind, string[]>;
interface ModelSummary { name: string; id: string; type: string; streaming: boolean; functions: boolean; vision: boolean; }
interface ProviderSummary { name: string; models: ModelSummary[]; }
interface ModelEditorState { originalName?: string; configuration: Record<string, unknown>; hasApiKey: boolean; }
interface Message { id: string; type: MessageType; title: string; content?: string; detail?: string; attachments?: string[]; timestamp: string; }
interface ActivityStep { id: string; title: string; content?: string; detail?: string; trace?: Record<string, unknown>; timestamp: string; running?: boolean; }
interface ActivityGroup { id: string; taskId?: string; title: string; timestamp: string; status: ActivityStatus; steps: ActivityStep[]; }
interface AgentState { name: string; status: 'running' | 'completed' | 'failed'; }
interface SessionSummary { session_id: string; name: string; workspace: string; source_workspace?: string | null; created_at?: string; updated_at?: string; has_work?: boolean; task_ids: string[]; }
interface UploadedAttachment { id: string; name: string; path?: string; size: number; mimeType: string; status: 'uploading' | 'ready' | 'error'; progress: number; error?: string; }
interface ExtensionStage { valid: boolean; components: unknown[]; error?: string; }
interface WorkspaceEntry { name: string; path: string; type: 'directory' | 'file'; size?: number | null; modified_at: number; }
interface WorkspaceFile { name: string; path: string; content: string; encoding?: 'utf-8' | 'base64'; size: number; modified_at: number; etag: string; mime_type: string; language: string; }
interface DeploySite { site_id: string; runtime: string; status: string; url?: string | null; port?: number | null; }
interface EnvironmentViewInfo { env_name: string; type: string; url: string; label?: string; password?: string | null; }
type InspectorTab = 'files' | 'activity' | 'inspector';
type MainView = 'chat' | 'canvas' | 'code' | 'science';
const WorkspaceEditor = lazy(() => import('./workspace/WorkspaceEditor'));
const VncView = lazy(() => import('./vnc/VncView'));
const CanvasView = lazy(() => import('./canvas'));
const IdeView = lazy(() => import('./ide/IdeView').then((module) => ({ default: module.IdeView })));
const ScienceView = lazy(() => import('./science/ScienceView').then((module) => ({ default: module.ScienceView })));
interface CapabilityDetail { kind: CapabilityKind; name: string; description: string; version: string; permission_mode: string; type?: string | string[]; enable_evolving: boolean; actions: string[]; parameter_schema?: Record<string, unknown>; usage?: string; configuration: Record<string, unknown>; editable: boolean; document: string; preview_document?: string; document_path?: string; language: 'markdown' | 'schema' | 'source'; }

// Same-origin by default: the page is served by the Vite dev server, which
// reverse-proxies /ws (and /env/vnc, /health) to the gateway. So a remote user
// only forwards the one UI port. A localStorage override / the ConnectionDialog
// can still point at an explicit gateway.
const wsOrigin = () => `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
const DEFAULT_ENDPOINT = `${wsOrigin()}/ws`;
const SESSION_KEY = 'autogenesis.gateway.session';
const SIDEBAR_WIDTH_KEY = 'autogenesis.layout.sidebar';
const SIDEBAR_COLLAPSED_KEY = 'autogenesis.layout.sidebarCollapsed';
const INSPECTOR_WIDTH_KEY = 'autogenesis.layout.inspector';
const SIDEBAR_WIDTH_RANGE = [190, 460] as const;
const INSPECTOR_WIDTH_RANGE = [300, 680] as const;

const clampWidth = (value: number, [min, max]: readonly [number, number]): number => Math.min(max, Math.max(min, value));

function readWidth(key: string, fallback: number): number {
  const raw = Number.parseInt(localStorage.getItem(key) ?? '', 10);
  return Number.isFinite(raw) ? raw : fallback;
}
const FILE_CHUNK_SIZE = 512 * 1024;
const EMPTY_CAPABILITIES: CapabilityCatalog = { agents: [], tools: [], skills: [], connectors: [], environments: [], workflows: [], commands: [], canvas: [] };
const EMPTY_SELECTION: CapabilitySelection = { agents: [], tools: [], skills: [], connectors: [], environments: [], workflows: [], commands: [], canvas: [] };
const CAPABILITY_META: Record<CapabilityKind, { label: string; icon: LucideIcon; description: string }> = {
  skills: { label: 'Skills', icon: GraduationCap, description: 'Reusable specialist workflows and domain knowledge.' },
  tools: { label: 'Tools', icon: Wrench, description: 'Actions the agent can call while it works.' },
  agents: { label: 'Agents', icon: Sparkles, description: 'Specialist agents available for delegation.' },
  connectors: { label: 'Connectors', icon: Cable, description: 'Connected data sources and external services.' },
  environments: { label: 'Environments', icon: Monitor, description: 'Session environments and their available actions.' },
  workflows: { label: 'Workflows', icon: Workflow, description: 'Reusable HTML programs that orchestrate agents and other capabilities.' },
  commands: { label: 'Commands', icon: SquareTerminal, description: 'Session control commands; run an enabled command from the composer.' },
  canvas: { label: 'Canvas', icon: Waypoints, description: 'Reusable visual flows saved from the canvas (a human-facing library, separate from agent workflows).' },
};
const CAPABILITY_KINDS = Object.keys(CAPABILITY_META) as CapabilityKind[];

/** Sidebar capability icon (lucide, matching the canvas + langflow style). */
function CapIcon({ kind, size = 16 }: { kind: CapabilityKind; size?: number }) {
  const Icon = CAPABILITY_META[kind].icon;
  return <Icon size={size} strokeWidth={1.9} />;
}

// Legacy builds hardcoded a direct gateway endpoint and persisted it. That
// bypasses the same-origin Vite proxy and breaks remote (forward-only-5173)
// access, so drop the stale value and fall back to the same-origin default.
const LEGACY_ENDPOINTS = new Set(['ws://127.0.0.1:9876/ws', 'ws://localhost:9876/ws']);
function initialEndpoint(): string {
  const stored = localStorage.getItem('autogenesis.gateway.endpoint');
  if (!stored || LEGACY_ENDPOINTS.has(stored)) {
    localStorage.removeItem('autogenesis.gateway.endpoint');
    return DEFAULT_ENDPOINT;
  }
  return stored;
}

export function App() {
  const [endpoint, setEndpoint] = useState(initialEndpoint);
  const [token, setToken] = useState(() => localStorage.getItem('autogenesis.gateway.token') ?? '');
  const [activeEndpoint, setActiveEndpoint] = useState(endpoint);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  // Restored on refresh so the same Gateway session is reused instead of a fresh one.
  const [sessionId, setSessionId] = useState<string | undefined>(() => localStorage.getItem(SESSION_KEY) ?? undefined);
  const [activeTaskId, setActiveTaskId] = useState<string>();
  const [messages, setMessages] = useState<Message[]>([]);
  const [activities, setActivities] = useState<ActivityGroup[]>([]);
  const [expandedActivities, setExpandedActivities] = useState<Set<string>>(new Set());
  const [agents, setAgents] = useState<AgentState[]>([]);
  const [catalog, setCatalog] = useState<CapabilityCatalog>(EMPTY_CAPABILITIES);
  const [selection, setSelection] = useState<CapabilitySelection>(EMPTY_SELECTION);
  const [draft, setDraft] = useState('');
  const setNotice = useAlertStore((state) => state.notify);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [theme, setTheme] = useState<Theme>(() => localStorage.getItem('autogenesis.theme') === 'dark' ? 'dark' : 'light');
  const [capabilitiesOpen, setCapabilitiesOpen] = useState(false);
  const [activeCapability, setActiveCapability] = useState<CapabilityKind>('skills');
  const [capabilitySearch, setCapabilitySearch] = useState('');
  const [details, setDetails] = useState<ActivityStep>();
  const [capabilityDetail, setCapabilityDetail] = useState<CapabilityDetail>();
  const [capabilityDetailLoading, setCapabilityDetailLoading] = useState(false);
  const [editingCapability, setEditingCapability] = useState<CapabilityDetail>();
  const [providers, setProviders] = useState<ProviderSummary[]>([]);
  const [modelsOpen, setModelsOpen] = useState(false);
  const [editingModel, setEditingModel] = useState<ModelEditorState>();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [deploys, setDeploys] = useState<DeploySite[]>([]);
  const [environmentView, setEnvironmentView] = useState<EnvironmentViewInfo>();
  const [attachments, setAttachments] = useState<UploadedAttachment[]>([]);
  const [extensionStage, setExtensionStage] = useState<ExtensionStage>({ valid: true, components: [] });
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [mainView, setMainView] = useState<MainView>('chat');
  // Chat's own transcript. Without it every message opened a NEW conversation,
  // and ctx.id — which is what memory is keyed by — was a fresh id each time:
  // the agent could not see what you had just asked it, so "make it subtract
  // instead" had no "it".
  const chatConversation = useRef<string | undefined>(undefined);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>('files');
  const [workspaceEntries, setWorkspaceEntries] = useState<Record<string, WorkspaceEntry[]>>({});
  const [expandedDirectories, setExpandedDirectories] = useState<Set<string>>(new Set());
  const [workspaceFile, setWorkspaceFile] = useState<WorkspaceFile>();
  const [workspaceLoading, setWorkspaceLoading] = useState(false);
  const [filePreview, setFilePreview] = useState(false);
  // Resizable column widths (px), persisted across refreshes.
  const [sidebarWidth, setSidebarWidth] = useState<number>(() => readWidth(SIDEBAR_WIDTH_KEY, 250));
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1');
  const [inspectorWidth, setInspectorWidth] = useState<number>(() => readWidth(INSPECTOR_WIDTH_KEY, 400));
  const socketRef = useRef<GatewaySocket | undefined>(undefined);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const sessionRef = useRef<string | undefined>(localStorage.getItem(SESSION_KEY) ?? undefined);
  const messageEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messageEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, activities]);

  useEffect(() => {
    localStorage.setItem('autogenesis.theme', theme);
    document.documentElement.classList.toggle('dark', theme === 'dark');
  }, [theme]);

  useEffect(() => {
    if (sessionId) localStorage.setItem(SESSION_KEY, sessionId);
    else localStorage.removeItem(SESSION_KEY);
  }, [sessionId]);

  useEffect(() => { localStorage.setItem(SIDEBAR_WIDTH_KEY, String(sidebarWidth)); }, [sidebarWidth]);
  useEffect(() => { localStorage.setItem(SIDEBAR_COLLAPSED_KEY, sidebarCollapsed ? '1' : '0'); }, [sidebarCollapsed]);
  useEffect(() => { localStorage.setItem(INSPECTOR_WIDTH_KEY, String(inspectorWidth)); }, [inspectorWidth]);

  const hydrateCapabilities = useCallback(async (socket: GatewaySocket, currentSessionId: string) => {
    const [catalogResponse, selectionResponse] = await Promise.all([
      socket.request('capability.list'),
      socket.request('session.capabilities.get', { session_id: currentSessionId }),
    ]);
    if (!catalogResponse.ok || !selectionResponse.ok) throw new Error('Could not load capability configuration');
    const available = asCatalog(catalogResponse.result);
    setCatalog(available);
    setSelection(asSelection(selectionResponse.result.capabilities));
  }, []);

  const refreshSessions = useCallback(async (socket: GatewaySocket) => {
    const response = await socket.request('session.list');
    if (!response.ok || !Array.isArray(response.result.sessions)) throw new Error('Could not load sessions');
    setSessions(response.result.sessions.filter(isSessionSummary));
  }, []);

  const loadModels = useCallback(async (socket: GatewaySocket) => {
    const response = await socket.request('model.list');
    if (!response.ok || !Array.isArray(response.result.providers)) throw new Error('Could not load model providers');
    setProviders(response.result.providers.filter(isProviderSummary));
  }, []);

  // Deployments are project-global (not per session), so this needs no session id.
  const loadDeploys = useCallback(async (socket: GatewaySocket) => {
    const response = await socket.request('deploy.list');
    if (response.ok && Array.isArray(response.result.sites)) {
      setDeploys(response.result.sites.map(asDeploySite).filter((site): site is DeploySite => Boolean(site)));
    }
  }, []);

  const loadAttachments = useCallback(async (socket: GatewaySocket, currentSessionId: string) => {
    const response = await socket.request('file.list', { session_id: currentSessionId });
    if (!response.ok || !Array.isArray(response.result.files)) throw new Error('Could not load uploaded files');
    setAttachments(response.result.files.map(asUploadedAttachment).filter((file): file is UploadedAttachment => file !== undefined));
  }, []);

  const loadExtensionStage = useCallback(async (socket: GatewaySocket, currentSessionId: string) => {
    const response = await socket.request('extension.stage.get', { session_id: currentSessionId });
    if (!response.ok || !isRecord(response.result.staging)) throw new Error(response.error?.message ?? 'Could not inspect staged extensions');
    const staging = response.result.staging;
    setExtensionStage({ valid: staging.valid !== false, components: Array.isArray(staging.components) ? staging.components : [], error: typeof staging.error === 'string' ? staging.error : undefined });
  }, []);

  const loadWorkspaceDirectory = useCallback(async (path = '') => {
    const socket = socketRef.current;
    const currentSessionId = sessionRef.current;
    if (!socket || !currentSessionId) return;
    const response = await socket.request('workspace.tree', { session_id: currentSessionId, path });
    if (!response.ok || !Array.isArray(response.result.entries)) throw new Error(response.error?.message ?? 'Could not load workspace');
    const entries = response.result.entries.filter(isWorkspaceEntry);
    setWorkspaceEntries((current) => ({ ...current, [path]: entries }));
  }, []);

  const openWorkspaceFile = useCallback(async (path: string) => {
    const socket = socketRef.current;
    const currentSessionId = sessionRef.current;
    if (!socket || !currentSessionId) return;
    setWorkspaceLoading(true);
    setFilePreview(false);
    try {
      const response = await socket.request('workspace.file.read', { session_id: currentSessionId, path });
      if (!response.ok) throw new Error(response.error?.message ?? 'Could not open file');
      const file = asWorkspaceFile(response.result);
      if (!file) throw new Error('Gateway returned an invalid file response');
      setWorkspaceFile(file);
      setInspectorTab('files');
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setWorkspaceLoading(false);
    }
  }, []);

  const toggleWorkspaceDirectory = useCallback(async (path: string) => {
    if (expandedDirectories.has(path)) {
      setExpandedDirectories((current) => { const next = new Set(current); next.delete(path); return next; });
      return;
    }
    try {
      if (!workspaceEntries[path]) await loadWorkspaceDirectory(path);
      setExpandedDirectories((current) => new Set(current).add(path));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  }, [expandedDirectories, loadWorkspaceDirectory, workspaceEntries]);

  useEffect(() => {
    setWorkspaceEntries({});
    setExpandedDirectories(new Set());
    setWorkspaceFile(undefined);
    if (sessionId) void loadWorkspaceDirectory().catch((error) => setNotice(error instanceof Error ? error.message : String(error)));
  }, [sessionId, loadWorkspaceDirectory]);

  /** This project's chat transcript, resumed rather than restarted.
   *
   * A refresh used to leave chatConversation empty, so the next message opened
   * a new one and the agent lost the thread — the same amnesia the per-message
   * conversation caused, just once per reload. Returns the events to replay. */
  const resumeChat = useCallback(async (socket: GatewaySocket, sessionId: string): Promise<GatewayEvent[]> => {
    const listed = await socket.request('conversation.list', { session_id: sessionId, view: 'chat' });
    const conversations = listed.ok
      ? (listed.result as { conversations?: Array<{ conversation_id: string }> }).conversations ?? [] : [];
    const latest = conversations[0]?.conversation_id;
    chatConversation.current = latest;
    if (!latest) return [];
    const replay = await socket.request('conversation.events', { session_id: sessionId, conversation_id: latest });
    return replay.ok ? (replay.result as { events?: GatewayEvent[] }).events ?? [] : [];
  }, []);

  const startSession = useCallback(async (socket: GatewaySocket) => {
    try {
      const hello = await socket.request('hello');
      if (!hello.ok) throw new Error(hello.error?.message ?? 'Gateway handshake failed');

      // Resume rather than create. sessionRef is a React ref, so a page refresh
      // arrives with nothing — and creating unconditionally minted one empty
      // project per reload, which is what filled the sidebar with identical
      // rows. Prefer the session this tab already had, then the most recently
      // worked-in project, and only create when there is nothing to open.
      const listed = await socket.request('session.list');
      const known = listed.ok && Array.isArray(listed.result.sessions)
        ? (listed.result.sessions as unknown as SessionSummary[]).filter(isSessionSummary) : [];
      const resume = known.find((item) => item.session_id === sessionRef.current)
        ?? known.find((item) => item.has_work !== false);

      if (resume) {
        sessionRef.current = resume.session_id;
        setSessionId(resume.session_id);
        await Promise.all([hydrateCapabilities(socket, resume.session_id), refreshSessions(socket), loadModels(socket), loadDeploys(socket), loadAttachments(socket, resume.session_id), loadExtensionStage(socket, resume.session_id)]);
        // Rebuild the transcript from this project's CHAT conversation, and
        // keep hold of it so the next message continues rather than restarts.
        const events = await resumeChat(socket, resume.session_id);
        setMessages([]);
        setActivities([]);
        for (const event of events) handleGatewayEvent(event);
        return;
      }

      if (sessionRef.current) {
        socket.forgetSession(sessionRef.current);
        sessionRef.current = undefined;
      }
      setSessionId(undefined);
      setMessages([]);
      setActivities([]);
      setAgents([]);
      setActiveTaskId(undefined);

      const response = await socket.request('session.create', { name: 'New project' });
      if (!response.ok || typeof response.result.session_id !== 'string') {
        throw new Error(response.error?.message ?? 'Could not create a session');
      }
      sessionRef.current = response.result.session_id;
      chatConversation.current = undefined;
      setSessionId(response.result.session_id);
      setMessages([{ id: 'welcome', type: 'system', title: 'Ready', content: 'Describe what you want Autogenesis to do.', timestamp: new Date().toISOString() }]);
      await Promise.all([hydrateCapabilities(socket, response.result.session_id), refreshSessions(socket), loadModels(socket), loadDeploys(socket), loadAttachments(socket, response.result.session_id), loadExtensionStage(socket, response.result.session_id)]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      setStatus('error');
    }
  }, [hydrateCapabilities, loadAttachments, loadExtensionStage, loadModels, loadDeploys, refreshSessions, resumeChat]);

  const updateAgent = useCallback((name: string, nextStatus: AgentState['status']) => {
    setAgents((current) => {
      const existing = current.find((agent) => agent.name === name);
      return existing
        ? current.map((agent) => agent.name === name ? { ...agent, status: nextStatus } : agent)
        : [...current, { name, status: nextStatus }];
    });
  }, []);

  const appendActivityStep = useCallback((event: GatewayEvent, step: ActivityStep, statusUpdate?: ActivityStatus) => {
    const taskId = event.task_id ?? 'session';
    setActivities((current) => {
      const index = current.findIndex((activity) => activity.taskId === taskId);
      const existing = index >= 0 ? current[index] : { id: taskId, taskId: event.task_id, title: event.type === 'task.submitted' ? 'Working on your request' : 'Agent activity', timestamp: event.timestamp, status: 'running' as const, steps: [] };
      const next = { ...existing, status: statusUpdate ?? existing.status, steps: [...existing.steps, step].slice(-250) };
      const updated = index >= 0 ? current.map((activity, position) => position === index ? next : activity) : [...current, next];
      return updated.slice(-30);
    });
  }, []);

  const finishActivity = useCallback((taskId: string | undefined, nextStatus: ActivityStatus) => {
    if (!taskId) return;
    setActivities((current) => current.map((activity) => activity.taskId === taskId ? { ...activity, status: nextStatus } : activity));
  }, []);

  const handleGatewayEvent = useCallback((event: GatewayEvent) => {
    if (event.type.startsWith('canvas.') || event.type.startsWith('science.') || event.type.startsWith('model.chat.')) return; // panels handle these themselves
    // The Gateway broadcasts every event to every client and expects each to
    // keep its own. Without this, work that is not this conversation's — a
    // canvas flow, which runs under its own scope — was rendered as if the user
    // had asked for it. Events with no session (capability and deploy changes)
    // are gateway-wide and belong to everyone.
    if (event.session_id && event.session_id !== sessionRef.current) return;
    if (event.type === 'session.capabilities.updated') {
      if (event.session_id === sessionRef.current) setSelection(asSelection(event.payload.capabilities));
      return;
    }
    if (event.type === 'capabilities.changed') {
      setCatalog(asCatalog(event.payload.capabilities));
      const name = typeof event.payload.name === 'string' ? humanize(event.payload.name) : 'Capabilities';
      const action = String(event.payload.action ?? 'updated');
      const kind = typeof event.payload.kind === 'string' ? event.payload.kind : 'capabilities';
      const message = action === 'registered'
        ? `${name} was added to ${kind} and enabled for this session.`
        : action === 'unregistered'
          ? `${name} was removed from ${kind}.`
          : `${name} was updated.`;
      setNotice(message);
      return;
    }
    if (event.type === 'capability.configured') {
      setNotice(`${humanize(String(event.payload.name ?? 'Capability'))} configuration was updated.`);
      return;
    }
    if (event.type === 'models.changed') {
      if (socketRef.current) void loadModels(socketRef.current);
      setNotice(`${humanize(String(event.payload.model && typeof event.payload.model === 'object' ? (event.payload.model as { name?: unknown }).name ?? 'Model' : 'Model'))} configuration was updated.`);
      return;
    }
    if (event.type === 'task.submitted') {
        const files = Array.isArray(event.payload.files) ? event.payload.files.filter((file): file is string => typeof file === 'string').map(fileName) : [];
        setMessages((items) => [...items, { id: `${event.task_id}:user`, type: 'user', title: 'You', content: String(event.payload.content ?? ''), attachments: files, timestamp: event.timestamp }]);
      appendActivityStep(event, activityStep(event), 'running');
      // The gateway titles a project from its first message and stamps it as
      // worked-in; both are what the sidebar orders and labels by, so re-read
      // the list rather than leaving "New project" sitting there.
      if (socketRef.current) void refreshSessions(socketRef.current);
      return;
    }
    if (event.type === 'command.executed') {
      if (event.session_id === sessionRef.current) {
        setMessages((items) => [...items, {
          id: `command:${event.seq_no}`,
          type: event.payload.success === false ? 'error' : 'system',
          title: String(event.payload.raw ?? 'Command'),
          content: String(event.payload.message ?? ''),
          detail: event.payload.data ? JSON.stringify(event.payload.data, null, 2) : undefined,
          timestamp: event.timestamp,
        }]);
      }
      return;
    }
    if (event.type === 'task.started' || event.type === 'trace.event') {
      const step = activityStep(event);
      if (step) appendActivityStep(event, step);
    }
    if (event.type === 'task.started') setActiveTaskId(event.task_id);
    if (event.type === 'trace.event') {
      const trace = event.payload;
      const name = String(trace.agent_name ?? 'agent');
      const traceType = String(trace.event_type ?? '');
      if (traceType === 'agent_start') updateAgent(name, 'running');
      if (traceType === 'agent_end') updateAgent(name, trace.success === false ? 'failed' : 'completed');
    }
    if (event.type === 'deploy.changed') {
      if (socketRef.current) void loadDeploys(socketRef.current);
      return;
    }
    if (event.type === 'environment.view') {
      setEnvironmentView(asEnvironmentView(event.payload));
      return;
    }
    if (event.type === 'task.completed') {
      setActiveTaskId(undefined);
      finishActivity(event.task_id, 'completed');
      setMessages((items) => [...items, finalMessage(event, 'assistant')]);
      void loadWorkspaceDirectory().catch(() => undefined);
      // A task may have deployed or torn down a site.
      if (socketRef.current) void loadDeploys(socketRef.current);
    }
    if (event.type === 'task.failed') {
      setActiveTaskId(undefined);
      finishActivity(event.task_id, 'failed');
      setMessages((items) => [...items, finalMessage(event, 'error')]);
    }
    if (event.type === 'task.cancelled') {
      setActiveTaskId(undefined);
      finishActivity(event.task_id, 'cancelled');
      setMessages((items) => [...items, finalMessage(event, 'system')]);
    }
  }, [appendActivityStep, finishActivity, loadModels, loadDeploys, loadWorkspaceDirectory, refreshSessions, updateAgent]);

  const connect = useCallback(() => {
    socketRef.current?.close();
    // Keep sessionRef/sessionId: startSession reuses the stored session when the
    // Gateway still has it (page refresh), or replaces it when it doesn't.
    setEnvironmentView(undefined);
    setMessages([]);
    setActivities([]);
    setAgents([]);
    setActiveTaskId(undefined);
    setAttachments([]);
    setNotice('');
    localStorage.setItem('autogenesis.gateway.endpoint', endpoint);
    localStorage.setItem('autogenesis.gateway.token', token);
    setActiveEndpoint(endpoint);

    const socket = new GatewaySocket(endpoint, token || undefined);
    socketRef.current = socket;
    socket.onStatus((nextStatus) => {
      setStatus(nextStatus);
      if (nextStatus === 'connected') void startSession(socket);
    });
    socket.onEvent(handleGatewayEvent);
    socket.connect();
  }, [endpoint, token, startSession, handleGatewayEvent]);

  useEffect(() => {
    connect();
    return () => socketRef.current?.close();
  }, [connect]);

  const redeploySite = async (siteId: string) => {
    const socket = socketRef.current;
    if (!socket) return;
    const response = await socket.request('deploy.redeploy', { site_id: siteId });
    if (!response.ok) setNotice(response.error?.message ?? 'Could not redeploy the site');
    await loadDeploys(socket);
  };

  const stopSite = async (siteId: string) => {
    const socket = socketRef.current;
    if (!socket) return;
    const response = await socket.request('deploy.stop', { site_id: siteId });
    if (!response.ok) setNotice(response.error?.message ?? 'Could not stop the site');
    await loadDeploys(socket);
  };

  const createNewSession = async () => {
    const socket = socketRef.current;
    if (!socket || status !== 'connected') return;
    if (attachments.some((attachment) => attachment.status === 'uploading')) {
      setNotice('Wait for file uploads to finish before creating a new project.');
      return;
    }
    // Already sitting in an untouched project: that IS a new project, so make
    // this a no-op rather than minting a second identical one. Otherwise the
    // button appears to do nothing (both rows read "New project") while quietly
    // leaving empty sessions behind in the gateway.
    const current = sessions.find((item) => item.session_id === sessionRef.current);
    if (current && current.has_work === false) {
      setNotice('You are already in a new project — describe what you want to do.');
      return;
    }
    try {
      sessionRef.current = undefined;
      setSessionId(undefined);
      setMessages([]);
      setActivities([]);
      setAgents([]);
      setActiveTaskId(undefined);
      setAttachments([]);
      setEnvironmentView(undefined);
      // Named "New project" only until the first message arrives — the gateway
      // retitles it from what is actually asked. A clock-stamped placeholder
      // told nobody which project was which.
      const response = await socket.request('session.create', { name: 'New project' });
      if (!response.ok || typeof response.result.session_id !== 'string') throw new Error(response.error?.message ?? 'Could not create a session');
      sessionRef.current = response.result.session_id;
      setSessionId(response.result.session_id);
      setMessages([{ id: 'welcome', type: 'system', title: 'Ready', content: 'Describe what you want Autogenesis to do.', timestamp: new Date().toISOString() }]);
      await Promise.all([hydrateCapabilities(socket, response.result.session_id), refreshSessions(socket), loadAttachments(socket, response.result.session_id), loadExtensionStage(socket, response.result.session_id)]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const selectSession = async (nextSession: SessionSummary) => {
    const socket = socketRef.current;
    if (!socket || nextSession.session_id === sessionRef.current) return;
    if (activeTaskId) {
      setNotice('Finish or stop the active task before switching projects.');
      return;
    }
    if (attachments.some((attachment) => attachment.status === 'uploading')) {
      setNotice('Wait for file uploads to finish before switching projects.');
      return;
    }
    try {
      const replay = await socket.request('session.events', { session_id: nextSession.session_id, after_seq: 0 });
      if (!replay.ok || !Array.isArray(replay.result.events)) throw new Error(replay.error?.message ?? 'Could not load the session');
      sessionRef.current = nextSession.session_id;
      setSessionId(nextSession.session_id);
      setMessages([]);
      setActivities([]);
      setAgents([]);
      setDetails(undefined);
      setEnvironmentView(undefined);
      setExpandedActivities(new Set());
      await Promise.all([hydrateCapabilities(socket, nextSession.session_id), loadAttachments(socket, nextSession.session_id), loadExtensionStage(socket, nextSession.session_id)]);
      for (const event of replay.result.events as GatewayEvent[]) handleGatewayEvent(event);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const submit = async (event?: FormEvent) => {
    event?.preventDefault();
    const readyAttachments = attachments.filter((attachment) => attachment.status === 'ready' && attachment.path);
    const content = draft.trim() || (readyAttachments.length ? 'Review the attached file(s) and determine the next best action.' : '');
    if (!content || !sessionRef.current || activeTaskId || attachments.some((attachment) => attachment.status === 'uploading')) return;
    setDraft('');
    try {
      const socket = socketRef.current;
      if (!socket) throw new Error('Gateway is not connected');
      if (content.startsWith('/')) {
        const response = await socket.request('command.execute', { session_id: sessionRef.current, raw: content });
        if (!response.ok) throw new Error(response.error?.message ?? 'Command failed');
        return;
      }
      const currentSession = sessions.find((session) => session.session_id === sessionRef.current);
      if (currentSession && isGenericSessionName(currentSession.name)) {
        const name = makeSessionTitle(content);
        const renamed = await socket.request('session.rename', { session_id: sessionRef.current, name });
        if (!renamed.ok) throw new Error(renamed.error?.message ?? 'Could not rename the session');
        setSessions((current) => current.map((session) => session.session_id === sessionRef.current ? { ...session, name } : session));
      }
      const response = await socket.request('task.submit', {
        session_id: sessionRef.current, content, view: 'chat',
        files: readyAttachments.map((attachment) => attachment.path),
        ...(chatConversation.current ? { conversation_id: chatConversation.current } : {}),
      });
      if (!response?.ok || typeof response.result.task_id !== 'string') throw new Error(response?.error?.message ?? 'Task submission failed');
      if (typeof response.result.conversation_id === 'string') chatConversation.current = response.result.conversation_id;
      setActiveTaskId(response.result.task_id);
      setAttachments([]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const cancelTask = async () => {
    if (!activeTaskId) return;
    await socketRef.current?.request('task.cancel', { task_id: activeTaskId });
  };

  const gatewayRequest = useCallback((method: string, params: Record<string, unknown> = {}) => {
    const socket = socketRef.current;
    if (!socket) return Promise.reject(new Error('Gateway is not connected'));
    return socket.request(method, params);
  }, []);

  const subscribeEvents = useCallback((listener: (event: GatewayEvent) => void) => {
    const socket = socketRef.current;
    if (!socket) return () => {};
    return socket.onEvent(listener);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status]);

  const uploadFiles = async (files: FileList | null) => {
    const socket = socketRef.current;
    const currentSessionId = sessionRef.current;
    if (!socket || !currentSessionId || !files?.length) return;
    for (const file of Array.from(files)) {
      const temporaryId = `local-${crypto.randomUUID()}`;
      let uploadId: string | undefined;
      setAttachments((current) => [...current, { id: temporaryId, name: file.name, size: file.size, mimeType: file.type || 'application/octet-stream', status: 'uploading', progress: 0 }]);
      try {
        const begun = await socket.request('file.upload.begin', { session_id: currentSessionId, name: file.name, size: file.size, mime_type: file.type || 'application/octet-stream' });
        if (!begun.ok || !isRecord(begun.result.file) || typeof begun.result.file.id !== 'string') throw new Error(begun.error?.message ?? 'Could not start file upload');
        uploadId = begun.result.file.id;
        setAttachments((current) => current.map((attachment) => attachment.id === temporaryId ? { ...attachment, id: uploadId as string } : attachment));
        for (let offset = 0; offset < file.size; offset += FILE_CHUNK_SIZE) {
          const chunk = await file.slice(offset, offset + FILE_CHUNK_SIZE).arrayBuffer();
          const uploaded = await socket.request('file.upload.chunk', { session_id: currentSessionId, file_id: uploadId, data: base64FromBuffer(chunk) });
          if (!uploaded.ok) throw new Error(uploaded.error?.message ?? 'File upload failed');
          const received = typeof uploaded.result.received === 'number' ? uploaded.result.received : offset + chunk.byteLength;
          setAttachments((current) => current.map((attachment) => attachment.id === uploadId ? { ...attachment, progress: received } : attachment));
        }
        const completed = await socket.request('file.upload.complete', { session_id: currentSessionId, file_id: uploadId });
        if (!completed.ok || !isRecord(completed.result.file)) throw new Error(completed.error?.message ?? 'Could not complete file upload');
        const uploadedFile = asUploadedAttachment(completed.result.file);
        if (!uploadedFile) throw new Error('Gateway returned an invalid uploaded file');
        setAttachments((current) => current.map((attachment) => attachment.id === uploadId ? uploadedFile : attachment));
      } catch (error) {
        if (uploadId) void socket.request('file.remove', { session_id: currentSessionId, file_id: uploadId });
        const message = error instanceof Error ? error.message : String(error);
        setAttachments((current) => current.map((attachment) => attachment.id === (uploadId ?? temporaryId) ? { ...attachment, status: 'error', error: message } : attachment));
        setNotice(message);
      }
    }
  };

  const removeAttachment = async (attachment: UploadedAttachment) => {
    if (attachment.status === 'uploading') return;
    try {
      if (attachment.status === 'ready' && sessionRef.current) {
        const response = await socketRef.current?.request('file.remove', { session_id: sessionRef.current, file_id: attachment.id });
        if (!response?.ok) throw new Error(response?.error?.message ?? 'Could not remove file');
      }
      setAttachments((current) => current.filter((item) => item.id !== attachment.id));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const toggleCapability = async (kind: CapabilityKind, name: string) => {
    if (!sessionRef.current) return;
    const next = { ...selection, [kind]: selection[kind].includes(name) ? selection[kind].filter((item) => item !== name) : [...selection[kind], name] };
    setSelection(next);
    try {
      const response = await socketRef.current?.request('session.capabilities.set', { session_id: sessionRef.current, capabilities: next });
      if (!response?.ok) throw new Error(response?.error?.message ?? 'Could not update capabilities');
      setSelection(asSelection(response.result.capabilities));
    } catch (error) {
      setSelection(selection);
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const toggleAllCapabilities = async (kind: CapabilityKind) => {
    if (!sessionRef.current) return;
    const next = { ...selection, [kind]: selection[kind].length === catalog[kind].length ? [] : catalog[kind].map((item) => item.name) };
    setSelection(next);
    try {
      const response = await socketRef.current?.request('session.capabilities.set', { session_id: sessionRef.current, capabilities: next });
      if (!response?.ok) throw new Error(response?.error?.message ?? 'Could not update capabilities');
    } catch (error) {
      setSelection(selection);
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const openCapabilityDetail = async (kind: CapabilityKind, name: string) => {
    const socket = socketRef.current;
    if (!socket) return;
    setCapabilityDetailLoading(true);
    try {
      const response = await socket.request('capability.get', { kind, name });
      if (!response.ok) throw new Error(response.error?.message ?? 'Could not load capability details');
      setCapabilityDetail(asCapabilityDetail(response.result));
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    } finally {
      setCapabilityDetailLoading(false);
    }
  };

  const configureCapability = async (detail: CapabilityDetail, configuration: Record<string, unknown>) => {
    try {
      const response = await socketRef.current?.request('capability.configure', { kind: detail.kind, name: detail.name, configuration });
      if (!response?.ok) throw new Error(response?.error?.message ?? 'Could not update capability configuration');
      const updated = asCapabilityDetail(response.result);
      setCapabilityDetail(updated);
      setEditingCapability(undefined);
      setNotice(`${humanize(updated.name)} configuration saved as version ${updated.version}.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const openModels = async () => {
    const socket = socketRef.current;
    if (!socket) return;
    try {
      await loadModels(socket);
      setModelsOpen(true);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const openModelEditor = async (name?: string) => {
    const socket = socketRef.current;
    if (!socket) return;
    if (!name) {
      setEditingModel({
        configuration: {
          model_name: 'openai/my-model', model_id: 'my-model', model_type: 'chat/completions', provider: 'openai',
          supports_streaming: true, supports_functions: true, supports_vision: false,
        },
        hasApiKey: false,
      });
      return;
    }
    try {
      const response = await socket.request('model.get', { name });
      if (!response.ok || !isRecord(response.result.configuration)) throw new Error(response.error?.message ?? 'Could not load model configuration');
      setEditingModel({ originalName: name, configuration: response.result.configuration, hasApiKey: Boolean(response.result.has_api_key) });
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const configureModel = async (editor: ModelEditorState, configuration: Record<string, unknown>, apiKey: string, clearApiKey: boolean) => {
    try {
      const params: Record<string, unknown> = { configuration };
      if (editor.originalName) params.original_name = editor.originalName;
      if (apiKey.trim()) params.api_key = apiKey.trim();
      if (clearApiKey) params.clear_api_key = true;
      const response = await socketRef.current?.request('model.configure', params);
      if (!response?.ok) throw new Error(response?.error?.message ?? 'Could not save model configuration');
      await loadModels(socketRef.current as GatewaySocket);
      setEditingModel(undefined);
      const savedModel = isRecord(response.result.model) ? response.result.model : {};
      setNotice(`${humanize(String(savedModel.name ?? 'Model'))} configuration saved.`);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
      throw error;
    }
  };

  const promoteStagedExtension = async () => {
    const socket = socketRef.current;
    const currentSessionId = sessionRef.current;
    if (!socket || !currentSessionId || !extensionStage.components.length) return;
    if (!extensionStage.valid) {
      setNotice(extensionStage.error ?? 'Fix staged extension validation errors before promotion.');
      return;
    }
    if (!window.confirm(`Promote ${extensionStage.components.length} staged extension component(s) to the shared extension root? Existing files will not be overwritten.`)) return;
    try {
      const response = await socket.request('extension.promote', { session_id: currentSessionId });
      if (!response.ok) throw new Error(response.error?.message ?? 'Extension promotion failed');
      const registered = Array.isArray(response.result.registered) ? response.result.registered.length : 0;
      setNotice(`Promoted ${registered} extension component${registered === 1 ? '' : 's'} to the shared extension root.`);
      await Promise.all([loadExtensionStage(socket, currentSessionId), refreshSessions(socket)]);
    } catch (error) {
      setNotice(error instanceof Error ? error.message : String(error));
    }
  };

  const handleComposerKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      void submit();
    }
  };

  const statusText = useMemo(() => status === 'connected' ? 'Connected' : status[0].toUpperCase() + status.slice(1), [status]);
  const capabilityItems = catalog[activeCapability].filter((item) => item.name.toLowerCase().includes(capabilitySearch.trim().toLowerCase()));
  // Grouped by recency, not by workspace. The workspace grouping was a level
  // that never varied — every project lives under the same output tree, so it
  // rendered one header over the whole list and bought nothing but a nesting.
  const projects = useMemo(() => {
    const groups: Array<[string, SessionSummary[]]> = [['Today', []], ['Previous 7 days', []], ['Older', []]];
    const now = Date.now();
    // Every project something has happened in, PLUS the one you are in right
    // now. A page refresh creates a session before the user has typed a word,
    // so listing them all filled the sidebar with identical "New project" rows
    // — but hiding every empty one made the New project button look broken,
    // since the thing it had just created was the one thing not shown. The
    // gateway still reports all of them: a reconnecting client asks this list
    // whether its own session still exists.
    const visible = sessions.filter((item) => item.has_work !== false || item.session_id === sessionId);
    for (const session of visible) {
      const age = now - new Date(session.updated_at ?? session.created_at ?? Date.now()).getTime();
      const bucket = age < 86_400_000 ? 0 : age < 604_800_000 ? 1 : 2;
      groups[bucket][1].push(session);
    }
    return groups.filter(([, items]) => items.length > 0);
  }, [sessions, sessionId]);
  const timeline = useMemo(() => [
    ...messages.map((message) => ({ id: message.id, timestamp: message.timestamp, type: 'message' as const, value: message })),
    ...activities.map((activity) => ({ id: activity.id, timestamp: activity.timestamp, type: 'activity' as const, value: activity })),
  ].sort((left, right) => left.timestamp.localeCompare(right.timestamp)), [messages, activities]);

  const startColumnDrag = (column: 'sidebar' | 'inspector') => (event: React.PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = column === 'sidebar' ? sidebarWidth : inspectorWidth;
    const onMove = (move: PointerEvent) => {
      // Sidebar grows as you drag right; the inspector (right column) grows as you drag left.
      const delta = column === 'sidebar' ? move.clientX - startX : startX - move.clientX;
      const range = column === 'sidebar' ? SIDEBAR_WIDTH_RANGE : INSPECTOR_WIDTH_RANGE;
      const next = clampWidth(startWidth + delta, range);
      if (column === 'sidebar') setSidebarWidth(next); else setInspectorWidth(next);
    };
    const onUp = () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
      document.body.classList.remove('col-resizing');
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp);
    document.body.classList.add('col-resizing');
  };

  return (
    <TooltipProvider skipDelayDuration={0}>
    <main className={`app-shell${mainView !== 'chat' ? ' canvas-wide' : ''}${sidebarCollapsed ? ' sidebar-collapsed' : ''}`} data-theme={theme} style={{ ['--sidebar-w' as string]: `${sidebarWidth}px`, ['--inspector-w' as string]: `${inspectorWidth}px` }}>
      <AlertDisplayArea />
      {/* Collapsed: the sidebar is out of the layout entirely, so this floating
          button is the only way back — and there is no column left to resize. */}
      {sidebarCollapsed ? (
        <button className="sidebar-reopen" onClick={() => setSidebarCollapsed(false)} title="Show sidebar" aria-label="Show sidebar"><PanelLeftOpen size={16} strokeWidth={1.9} /></button>
      ) : (
        <div className="col-resizer col-resizer-left" onPointerDown={startColumnDrag('sidebar')} role="separator" aria-orientation="vertical" aria-label="Resize sidebar" />
      )}
      {mainView === 'chat' ? <div className="col-resizer col-resizer-right" onPointerDown={startColumnDrag('inspector')} role="separator" aria-orientation="vertical" aria-label="Resize workspace panel" /> : null}
      <aside className="sidebar">
        {/* Navigation: which project, which view. Never shrinks, and is the
            same in all four views — a project is the level ABOVE them, so
            switching to Code must not take the project list away. */}
        <div className="sidebar-nav">
        <div className="brand"><span className="brand-mark"><Sparkles size={16} strokeWidth={2} /></span><span>Autogenesis</span><button className="sidebar-collapse" onClick={() => setSidebarCollapsed(true)} title="Hide sidebar" aria-label="Hide sidebar"><PanelLeftClose size={16} strokeWidth={1.9} /></button></div>
        <button className="new-chat" onClick={() => void createNewSession()} disabled={status !== 'connected'}><Plus size={16} /> New project</button>
        <div className="sidebar-section projects-section">
          <p className="eyebrow">Projects</p>
          {projects.length ? projects.map(([bucket, bucketSessions]) => <div className="project-group" key={bucket}><div className="project-name">{bucket}</div>{bucketSessions.map((projectSession) => <button className={`project-session ${projectSession.session_id === sessionId ? 'selected' : ''}`} key={projectSession.session_id} title={projectSession.name} onClick={() => void selectSession(projectSession)}><span className="session-dot" /><span>{projectSession.name || `Project ${projectSession.session_id.slice(0, 8)}`}</span><em>{projectSession.task_ids.length}</em></button>)}</div>) : <p className="empty">Projects appear here once you ask for something.</p>}
        </div>
        <nav className="sidebar-section capability-nav view-nav" aria-label="Views">
          <p className="eyebrow">Views</p>
          <button className={mainView === 'chat' ? 'view-active' : ''} onClick={() => setMainView('chat')}><span><MessageSquare size={16} strokeWidth={1.9} /></span><strong>Chat</strong></button>
          <button className={mainView === 'canvas' ? 'view-active' : ''} onClick={() => setMainView('canvas')}><span><Waypoints size={16} strokeWidth={1.9} /></span><strong>Canvas</strong></button>
          <button className={mainView === 'code' ? 'view-active' : ''} onClick={() => setMainView('code')}><span><Code2 size={16} strokeWidth={1.9} /></span><strong>Code</strong></button>
          <button className={mainView === 'science' ? 'view-active' : ''} onClick={() => setMainView('science')}><span><FlaskConical size={16} strokeWidth={1.9} /></span><strong>Science</strong></button>
        </nav>
        </div>
        {/* Everything below is reference, not navigation: it takes whatever
            room is left and scrolls, rather than squeezing the project list to
            nothing on a short window. */}
        <div className="sidebar-rest">
        <nav className="sidebar-section capability-nav" aria-label="Capabilities">
          <p className="eyebrow">Capabilities</p>
          {CAPABILITY_KINDS.map((kind) => <button key={kind} onClick={() => { setActiveCapability(kind); setCapabilitySearch(''); setCapabilitiesOpen(true); }}><span><CapIcon kind={kind} /></span><strong>{CAPABILITY_META[kind].label}</strong><em>{selection[kind].length}</em></button>)}
        </nav>
        <div className="sidebar-section model-nav"><p className="eyebrow">Models</p><button onClick={() => void openModels()}><span><Boxes size={16} strokeWidth={1.9} /></span><strong>Providers</strong><em>{providers.reduce((count, provider) => count + provider.models.length, 0)}</em></button></div>
        <div className="sidebar-section agents-section">
          <p className="eyebrow">Active agents</p>
          {agents.length ? agents.map((agent) => <div className="agent-row" key={agent.name}><span className={`agent-state ${agent.status}`} /><span>{agent.name}</span></div>) : <p className="empty">Agents appear while a task runs.</p>}
        </div>
        <div className="sidebar-section deploy-section">
          <p className="eyebrow">Deployments <button className="section-refresh" title="Refresh" onClick={() => { if (socketRef.current) void loadDeploys(socketRef.current); }}><RefreshCw size={12} /></button></p>
          {deploys.length ? deploys.map((site) => <div className={`deploy-row ${site.status}`} key={site.site_id}>
            <span className={`deploy-dot ${site.status}`} title={site.status} />
            <div className="deploy-meta">
              {site.url && site.status === 'running'
                ? <a href={site.url} target="_blank" rel="noreferrer" title={site.url}>{site.site_id}</a>
                : <span title={site.site_id}>{site.site_id}</span>}
              <small>{site.runtime} · {site.status}</small>
            </div>
            {site.status === 'running'
              ? <button className="deploy-action" title="Stop" onClick={() => void stopSite(site.site_id)}>■</button>
              : <button className="deploy-action" title="Redeploy" onClick={() => void redeploySite(site.site_id)}>↻</button>}
          </div>) : <p className="empty">No deployed services yet.</p>}
        </div>
        </div>
        {/* Pinned to the bottom rather than scrolling away with the sections
            above it: theme and connection are settings, always reachable. */}
        <div className="sidebar-footer"><button className="text-button" onClick={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')}>{theme === 'dark' ? <><Sun size={14} /> Light theme</> : <><Moon size={14} /> Dark theme</>}</button><button className="text-button" onClick={() => setSettingsOpen(true)}><Settings size={14} /> Connection</button></div>
      </aside>

      {/* No page header here: VS Code brings its own full chrome, so the usual
          eyebrow+title bar would be a second wasted strip above it. IdeView's
          own slim toolbar carries the title, status and controls instead. */}
      {mainView === 'science' ? <section className="conversation science-mode">
        <Suspense fallback={<div className="workspace-placeholder">Loading workstation…</div>}>
          <ScienceView request={gatewayRequest} subscribe={subscribeEvents} sessionId={sessionId} connected={status === 'connected'}
            status={status} statusText={statusText} onOpenNav={() => setMobileNavOpen(true)} />
        </Suspense>
      </section> : mainView === 'code' ? <section className="conversation ide-mode">
        <Suspense fallback={<div className="workspace-placeholder">Loading editor…</div>}>
          <IdeView request={gatewayRequest} sessionId={sessionId} connected={status === 'connected'}
            status={status} statusText={statusText} onOpenNav={() => setMobileNavOpen(true)} />
        </Suspense>
      </section> : mainView === 'canvas' ? <section className="conversation canvas-mode">
        <header className="topbar">
          <div className="header-title"><button className="mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">☰</button><div><p className="eyebrow">Visual orchestration</p><h1>Canvas</h1></div></div>
          <div className="connection"><span className={`connection-dot ${status}`} />{statusText}</div>
        </header>
        <Suspense fallback={<div className="workspace-placeholder">Loading canvas…</div>}>
          <CanvasView request={gatewayRequest} subscribe={subscribeEvents} sessionId={sessionId} connected={status === 'connected'} theme={theme} onNotice={setNotice} />
        </Suspense>
      </section> : <section className="conversation">
        <header className="topbar">
          <div className="header-title"><button className="mobile-menu" onClick={() => setMobileNavOpen(true)} aria-label="Open navigation">☰</button><div><p className="eyebrow">Workspace agent</p><h1>New task</h1></div></div>
          <div className="connection">{extensionStage.components.length ? <button className={`stage-action ${extensionStage.valid ? '' : 'invalid'}`} disabled={!sessionId} onClick={() => void promoteStagedExtension()} title={extensionStage.error ?? 'Promote validated staged extensions'}>⇧ Promote {extensionStage.components.length} extension{extensionStage.components.length === 1 ? '' : 's'}</button> : null}<span className={`connection-dot ${status}`} />{statusText}<button onClick={() => setSettingsOpen(true)}>Configure</button></div>
        </header>
        <div className="message-list">
          {environmentView ? <EnvironmentLive view={environmentView} onClose={() => setEnvironmentView(undefined)} /> : null}
          {timeline.length <= 1 ? <QuickStart onSelect={setDraft} /> : null}
          {timeline.map((item) => item.type === 'message'
            ? <MessageCard key={item.id} message={item.value} />
            : <ActivityCard key={item.id} activity={item.value} expanded={expandedActivities.has(item.id)} onToggle={() => setExpandedActivities((current) => { const next = new Set(current); next.has(item.id) ? next.delete(item.id) : next.add(item.id); return next; })} onSelect={(step) => { setDetails(step); setInspectorTab('inspector'); }} />)}
          <div ref={messageEndRef} />
        </div>
        <div className="composer-wrap">
          <form className="composer" onSubmit={submit}>
            <input ref={fileInputRef} className="file-input" type="file" multiple onChange={(event) => { void uploadFiles(event.target.files); event.target.value = ''; }} />
            {attachments.length ? <div className="attachment-list">{attachments.map((attachment) => <div className={`attachment-chip ${attachment.status}`} key={attachment.id}><span className="attachment-icon">{attachment.status === 'uploading' ? '◌' : attachment.status === 'error' ? '!' : '⌕'}</span><span className="attachment-copy"><strong>{attachment.name}</strong><small>{attachment.status === 'uploading' ? `Uploading ${formatFileSize(attachment.progress)} of ${formatFileSize(attachment.size)}` : attachment.status === 'error' ? attachment.error ?? 'Upload failed' : formatFileSize(attachment.size)}</small></span><button type="button" onClick={() => void removeAttachment(attachment)} disabled={attachment.status === 'uploading'} aria-label={`Remove ${attachment.name}`}>×</button></div>)}</div> : null}
            <textarea value={draft} onChange={(event) => setDraft(event.target.value)} onKeyDown={handleComposerKeyDown} placeholder="Ask Autogenesis to investigate, implement, or review…" disabled={status !== 'connected' || Boolean(activeTaskId)} rows={3} />
            <div className="composer-actions"><button className="attach-file" type="button" onClick={() => fileInputRef.current?.click()} disabled={status !== 'connected' || Boolean(activeTaskId)}>⌕ Attach files</button><span>Enter to send · Shift+Enter for a new line</span>{activeTaskId ? <button type="button" className="stop" onClick={cancelTask}>■ Stop task</button> : <button type="submit" disabled={(!draft.trim() && !attachments.some((attachment) => attachment.status === 'ready')) || attachments.some((attachment) => attachment.status === 'uploading') || status !== 'connected'}>Send <span>↵</span></button>}</div>
          </form>
        </div>
      </section>}

      {mainView === 'chat' ? <WorkspaceWorkbench
        tab={inspectorTab}
        onTab={setInspectorTab}
        entries={workspaceEntries}
        expanded={expandedDirectories}
        selectedFile={workspaceFile}
        loading={workspaceLoading}
        preview={filePreview}
        theme={theme}
        activeTaskId={activeTaskId}
        endpoint={activeEndpoint}
        details={details}
        onToggleDirectory={(path) => void toggleWorkspaceDirectory(path)}
        onOpenFile={(path) => void openWorkspaceFile(path)}
        onRefresh={() => { void loadWorkspaceDirectory(); if (workspaceFile) void openWorkspaceFile(workspaceFile.path); }}
        onPreview={setFilePreview}
      /> : null}

      {capabilitiesOpen ? <CapabilityDialog activeKind={activeCapability} catalog={catalog} selection={selection} items={capabilityItems} search={capabilitySearch} onSearch={setCapabilitySearch} onSelectKind={(kind) => { setActiveCapability(kind); setCapabilitySearch(''); }} onToggle={toggleCapability} onToggleAll={toggleAllCapabilities} onInspect={openCapabilityDetail} onClose={() => setCapabilitiesOpen(false)} /> : null}
      {capabilityDetailLoading ? <CapabilityDetailDialog loading onClose={() => setCapabilityDetailLoading(false)} /> : null}
      {capabilityDetail ? <CapabilityDetailDialog detail={capabilityDetail} onEdit={() => setEditingCapability(capabilityDetail)} onClose={() => setCapabilityDetail(undefined)} /> : null}
      {editingCapability ? <CapabilityConfigDialog detail={editingCapability} onSave={configureCapability} onClose={() => setEditingCapability(undefined)} /> : null}
      {modelsOpen ? <ModelsDialog providers={providers} onAdd={() => void openModelEditor()} onEdit={(name) => void openModelEditor(name)} onClose={() => setModelsOpen(false)} /> : null}
      {editingModel ? <ModelConfigDialog editor={editingModel} onSave={configureModel} onClose={() => setEditingModel(undefined)} /> : null}
      {settingsOpen ? <ConnectionDialog endpoint={endpoint} token={token} onEndpoint={setEndpoint} onToken={setToken} onClose={() => setSettingsOpen(false)} onConnect={() => { setSettingsOpen(false); connect(); }} /> : null}
      {mobileNavOpen ? <MobileNavigation projects={projects} sessionId={sessionId} selection={selection} agents={agents} status={status} theme={theme} onClose={() => setMobileNavOpen(false)} onCreateSession={createNewSession} onSelectSession={selectSession} onOpenCapabilities={(kind) => { setActiveCapability(kind); setCapabilitySearch(''); setCapabilitiesOpen(true); }} onToggleTheme={() => setTheme((current) => current === 'dark' ? 'light' : 'dark')} onOpenConnection={() => setSettingsOpen(true)} /> : null}
    </main>
    </TooltipProvider>
  );
}

function WorkspaceWorkbench({ tab, onTab, entries, expanded, selectedFile, loading, preview, theme, activeTaskId, endpoint, details, onToggleDirectory, onOpenFile, onRefresh, onPreview }: {
  tab: InspectorTab;
  onTab: (tab: InspectorTab) => void;
  entries: Record<string, WorkspaceEntry[]>;
  expanded: Set<string>;
  selectedFile?: WorkspaceFile;
  loading: boolean;
  preview: boolean;
  theme: Theme;
  activeTaskId?: string;
  endpoint: string;
  details?: ActivityStep;
  onToggleDirectory: (path: string) => void;
  onOpenFile: (path: string) => void;
  onRefresh: () => void;
  onPreview: (preview: boolean) => void;
}) {
  const isMedia = selectedFile?.encoding === 'base64';
  // Media renders itself; source/preview toggling and copying base64 make no sense.
  const canPreview = !isMedia && (selectedFile?.language === 'markdown' || selectedFile?.language === 'html');
  return <aside className="inspector workspace-workbench">
    <nav className="workbench-tabs" aria-label="Workspace panel">
      {(['files', 'activity', 'inspector'] as InspectorTab[]).map((item) => <button className={tab === item ? 'active' : ''} key={item} onClick={() => onTab(item)}>{humanize(item)}</button>)}
    </nav>
    {tab === 'files' ? <div className="workspace-panel">
      <header className="workspace-toolbar"><div><strong>Workspace</strong><small>Current session</small></div><button onClick={onRefresh} title="Refresh workspace">↻</button></header>
      <div className="workspace-tree" role="tree">
        <WorkspaceTree path="" entries={entries} expanded={expanded} selectedPath={selectedFile?.path} onToggle={onToggleDirectory} onOpen={onOpenFile} />
      </div>
      <section className="workspace-viewer">
        {selectedFile ? <>
          <header className="file-toolbar"><div title={selectedFile.path}><strong>{selectedFile.name}</strong><small>{selectedFile.path} · {formatFileSize(selectedFile.size)}</small></div><div>{canPreview ? <button className={preview ? 'active' : ''} onClick={() => onPreview(!preview)}>{preview ? 'Source' : 'Preview'}</button> : null}{isMedia ? null : <button onClick={() => navigator.clipboard?.writeText(selectedFile.content)}>Copy</button>}</div></header>
          <div className="file-editor">{mediaSource(selectedFile)
            ? <MediaDocument file={selectedFile} src={mediaSource(selectedFile)!} />
            : preview && selectedFile.language === 'markdown'
              ? <MarkdownDocument content={selectedFile.content} />
              : preview && selectedFile.language === 'html'
                ? <iframe title={`${selectedFile.name} preview`} sandbox="" srcDoc={selectedFile.content} />
                : <Suspense fallback={<div className="workspace-placeholder">Loading editor…</div>}><WorkspaceEditor filePath={selectedFile.path} language={selectedFile.language} content={selectedFile.content} theme={theme} /></Suspense>}
          </div>
        </> : <div className="workspace-placeholder">{loading ? 'Opening file…' : 'Select a file to inspect its contents.'}</div>}
      </section>
    </div> : tab === 'activity' ? <div className="workbench-section"><p className="eyebrow">Activity</p>{activeTaskId ? <div className="activity-running"><span className="pulse" /> Task running</div> : <div className="activity-idle">Waiting for a task</div>}<p className="eyebrow inspector-heading">Gateway</p><code>{endpoint}</code></div> : <div className="workbench-section"><p className="eyebrow">Selected step</p>{details ? <div className="detail-card"><strong>{details.title}</strong>{details.trace ? <StructuredTrace trace={details.trace} compact /> : <pre>{details.detail ?? details.content ?? 'No details'}</pre>}</div> : <p className="empty">Expand an activity and select a step to inspect it.</p>}</div>}
  </aside>;
}

function WorkspaceTree({ path, entries, expanded, selectedPath, onToggle, onOpen, depth = 0 }: { path: string; entries: Record<string, WorkspaceEntry[]>; expanded: Set<string>; selectedPath?: string; onToggle: (path: string) => void; onOpen: (path: string) => void; depth?: number }) {
  const children = entries[path] ?? [];
  if (!children.length && depth === 0) return <p className="workspace-empty">Workspace is empty.</p>;
  return <>{children.map((entry) => entry.type === 'directory' ? <div key={entry.path} role="treeitem" aria-expanded={expanded.has(entry.path)}>
    <button className="tree-row directory" style={{ paddingLeft: 10 + depth * 14 }} onClick={() => onToggle(entry.path)}><span>{expanded.has(entry.path) ? '⌄' : '›'}</span><i>▱</i><strong>{entry.name}</strong></button>
    {expanded.has(entry.path) ? <WorkspaceTree path={entry.path} entries={entries} expanded={expanded} selectedPath={selectedPath} onToggle={onToggle} onOpen={onOpen} depth={depth + 1} /> : null}
  </div> : <button key={entry.path} role="treeitem" className={`tree-row file ${selectedPath === entry.path ? 'selected' : ''}`} style={{ paddingLeft: 10 + depth * 14 }} onClick={() => onOpen(entry.path)}><span /><i>{fileIcon(entry.name)}</i><strong>{entry.name}</strong></button>)}</>;
}

function fileIcon(name: string): string {
  const extension = name.split('.').pop()?.toLowerCase();
  if (extension === 'md') return 'M↓';
  if (extension === 'py') return 'Py';
  if (['js', 'jsx', 'ts', 'tsx'].includes(extension ?? '')) return 'JS';
  if (['html', 'htm'].includes(extension ?? '')) return '<>';
  if (['json', 'yaml', 'yml', 'toml'].includes(extension ?? '')) return '{}';
  return '·';
}

function MessageCard({ message }: { message: Message }) {
  return <article className={`message-card ${message.type}`}><div className="message-avatar">{message.type === 'user' ? 'You' : '✦'}</div><div className="message-content"><div className="message-heading"><strong>{message.title}</strong><time>{formatTime(message.timestamp)}</time></div>{message.content ? message.type === 'user' ? <p>{message.content}</p> : <MessageMarkdown content={message.content} /> : null}{message.attachments?.length ? <div className="message-files">{message.attachments.map((attachment) => <span key={attachment}>⌕ {attachment}</span>)}</div> : null}</div></article>;
}

function ActivityCard({ activity, expanded, onToggle, onSelect }: { activity: ActivityGroup; expanded: boolean; onToggle: () => void; onSelect: (step: ActivityStep) => void }) {
  const label = activity.status === 'running' ? 'Working' : activity.status === 'completed' ? 'Completed' : activity.status === 'cancelled' ? 'Cancelled' : 'Failed';
  return <section className={`activity-card ${activity.status}`}><button className="activity-summary" onClick={onToggle} aria-expanded={expanded}><span className="activity-icon">{activity.status === 'running' ? '◌' : '✓'}</span><span className="activity-copy"><strong>{activity.title}</strong><small>{activity.steps.length} execution step{activity.steps.length === 1 ? '' : 's'} · {label}</small></span><span className="activity-chevron">{expanded ? '⌃' : '⌄'}</span></button>{expanded ? <div className="activity-steps">{activity.steps.map((step) => <details className="activity-step-card" key={step.id} onToggle={(event) => { if (event.currentTarget.open) onSelect(step); }}><summary className="activity-step"><span className="step-dot" /><span><strong>{step.title}</strong>{step.content ? <small>{step.content}</small> : null}</span><time>{formatTime(step.timestamp)}</time></summary>{step.trace ? <StructuredTrace trace={step.trace} /> : <div className="trace-sections"><TraceSection label="Details" value={step.detail ?? step.content} /></div>}</details>)}</div> : null}</section>;
}

function StructuredTrace({ trace, compact = false }: { trace: Record<string, unknown>; compact?: boolean }) {
  const input = isRecord(trace.input) ? trace.input : undefined;
  const command = input && (input.command ?? input.cmd ?? input.script);
  const reasoning = traceReasoning(trace);
  const output = trace.output ?? (reasoning ? undefined : trace.message);
  const metadata = isRecord(trace.metadata) ? trace.metadata : undefined;
  const inputWithoutCommand = input ? Object.fromEntries(Object.entries(input).filter(([key]) => !['command', 'cmd', 'script'].includes(key))) : undefined;
  return <div className={`trace-sections ${compact ? 'compact' : ''}`}>
    <div className="trace-facts">{typeof trace.step_number === 'number' ? <span>Step {trace.step_number}</span> : null}{typeof trace.action_index === 'number' ? <span>Action {trace.action_index + 1}</span> : null}{typeof trace.duration_ms === 'number' ? <span>{formatDuration(trace.duration_ms)}</span> : null}{typeof trace.success === 'boolean' ? <span className={trace.success ? 'success' : 'failure'}>{trace.success ? 'Success' : 'Failed'}</span> : null}</div>
    {reasoning ? <TraceSection label="Reasoning" value={reasoning} type="reasoning" /> : null}
    {command !== undefined ? <TraceSection label="Command" value={command} type="command" /> : null}
    {inputWithoutCommand && Object.keys(inputWithoutCommand).length ? <TraceSection label={trace.action_name ? 'Arguments' : 'Input'} value={inputWithoutCommand} /> : null}
    {output !== undefined && output !== null && output !== '' ? <TraceSection label="Output" value={output} type="output" /> : null}
    {trace.error ? <TraceSection label="Error" value={trace.error} type="error" /> : null}
    {metadata && Object.keys(metadata).some((key) => key !== 'success') ? <TraceSection label="Metadata" value={metadata} /> : null}
    {!compact ? <details className="raw-event"><summary>Raw event</summary><pre><code>{JSON.stringify(trace, null, 2)}</code></pre></details> : null}
  </div>;
}

function TraceSection({ label, value, type = 'data' }: { label: string; value: unknown; type?: 'data' | 'reasoning' | 'command' | 'output' | 'error' }) {
  if (value === undefined || value === null || value === '') return null;
  const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
  return <section className={`trace-section ${type}`}><header><span>{traceIcon(type)}</span><strong>{label}</strong><button onClick={() => navigator.clipboard?.writeText(text)}>Copy</button></header>{type === 'reasoning' ? <div className="trace-reasoning"><ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown></div> : <pre><code>{text}</code></pre>}</section>;
}

function traceReasoning(trace: Record<string, unknown>): string | undefined {
  if (typeof trace.reasoning === 'string') return trace.reasoning;
  if (String(trace.event_type) !== 'agent_call' || typeof trace.message !== 'string') return undefined;
  const legacy = trace.message.match(/^\{'reasoning':\s*(?:None|'([\s\S]*)')\}$/);
  return legacy?.[1]?.replaceAll("\\n", "\n").replaceAll("\\'", "'") ?? trace.message;
}

function traceIcon(type: string): string { return type === 'reasoning' ? '✦' : type === 'command' ? '›_' : type === 'output' ? '↳' : type === 'error' ? '!' : '{}'; }
function formatDuration(value: number): string { return value < 1000 ? `${Math.round(value)} ms` : `${(value / 1000).toFixed(2)} s`; }

function QuickStart({ onSelect }: { onSelect: (prompt: string) => void }) {
  const prompts = [
    ['Review this project', 'Find the highest-impact issues and suggest fixes.'],
    ['Plan a feature', 'Turn a requirement into an implementation plan.'],
    ['Explain the architecture', 'Trace the main modules and their responsibilities.'],
    ['Investigate a problem', 'Gather evidence, form hypotheses, and recommend next steps.'],
  ];
  return <section className="quick-start"><p className="eyebrow">Get started</p><h2>What would you like to work on?</h2><p>Choose a starting point or describe a task in your own words.</p><div className="quick-prompts">{prompts.map(([title, prompt]) => <button key={title} onClick={() => onSelect(prompt)}><strong>{title}</strong><span>{prompt}</span></button>)}</div></section>;
}

function MobileNavigation({ projects, sessionId, selection, agents, status, theme, onClose, onCreateSession, onSelectSession, onOpenCapabilities, onToggleTheme, onOpenConnection }: { projects: [string, SessionSummary[]][]; sessionId?: string; selection: CapabilitySelection; agents: AgentState[]; status: ConnectionStatus; theme: Theme; onClose: () => void; onCreateSession: () => Promise<void>; onSelectSession: (session: SessionSummary) => Promise<void>; onOpenCapabilities: (kind: CapabilityKind) => void; onToggleTheme: () => void; onOpenConnection: () => void }) {
  return <div className="mobile-nav-backdrop" onClick={onClose}><aside className="mobile-nav" onClick={(event) => event.stopPropagation()}><div className="brand"><span className="brand-mark"><Sparkles size={16} strokeWidth={2} /></span><span>Autogenesis</span><button className="mobile-close" onClick={onClose} aria-label="Close navigation">×</button></div><button className="new-chat" disabled={status !== 'connected'} onClick={() => { void onCreateSession(); onClose(); }}><Plus size={16} /> New project</button><div className="sidebar-section projects-section"><p className="eyebrow">Projects</p>{projects.map(([bucket, bucketSessions]) => <div className="project-group" key={bucket}><div className="project-name">{bucket}</div>{bucketSessions.map((session) => <button className={`project-session ${session.session_id === sessionId ? 'selected' : ''}`} key={session.session_id} onClick={() => { void onSelectSession(session); onClose(); }}><span className="session-dot" /><span>{session.name}</span><em>{session.task_ids.length}</em></button>)}</div>)}</div><nav className="sidebar-section capability-nav"><p className="eyebrow">Capabilities</p>{CAPABILITY_KINDS.map((kind) => <button key={kind} onClick={() => { onOpenCapabilities(kind); onClose(); }}><span><CapIcon kind={kind} /></span><strong>{CAPABILITY_META[kind].label}</strong><em>{selection[kind].length}</em></button>)}</nav><div className="sidebar-section agents-section"><p className="eyebrow">Active agents</p>{agents.length ? agents.map((agent) => <div className="agent-row" key={agent.name}><span className={`agent-state ${agent.status}`} /><span>{agent.name}</span></div>) : <p className="empty">Agents appear while a task runs.</p>}</div><div className="sidebar-footer"><button className="text-button" onClick={onToggleTheme}>{theme === 'dark' ? <><Sun size={14} /> Light theme</> : <><Moon size={14} /> Dark theme</>}</button><button className="text-button" onClick={() => { onOpenConnection(); onClose(); }}><Settings size={14} /> Connection</button></div></aside></div>;
}

function CapabilityDialog({ activeKind, catalog, selection, items, search, onSearch, onSelectKind, onToggle, onToggleAll, onInspect, onClose }: { activeKind: CapabilityKind; catalog: CapabilityCatalog; selection: CapabilitySelection; items: CapabilityItem[]; search: string; onSearch: (value: string) => void; onSelectKind: (kind: CapabilityKind) => void; onToggle: (kind: CapabilityKind, name: string) => void; onToggleAll: (kind: CapabilityKind) => void; onInspect: (kind: CapabilityKind, name: string) => void; onClose: () => void }) {
  const meta = CAPABILITY_META[activeKind];
  const allEnabled = catalog[activeKind].length > 0 && selection[activeKind].length === catalog[activeKind].length;
  return <div className="modal-backdrop capability-backdrop" onClick={onClose}><section className="capability-dialog" onClick={(event) => event.stopPropagation()}><aside className="capability-menu"><div className="modal-title"><h2>Capabilities</h2></div><p className="eyebrow">Browse capabilities</p>{CAPABILITY_KINDS.map((kind) => <button role="tab" aria-selected={kind === activeKind} className={kind === activeKind ? 'active' : ''} key={kind} onClick={() => onSelectKind(kind)}><span><CapIcon kind={kind} /></span>{CAPABILITY_META[kind].label}<em>{selection[kind].length}</em></button>)}</aside><section className="capability-content" role="tabpanel"><header><div><p className="eyebrow">Capabilities · {meta.label}</p><h2><CapIcon kind={activeKind} size={20} /> {meta.label}</h2><p>{meta.description}</p></div><button className="close-dialog" onClick={onClose}>×</button></header><div className="capability-toolbar"><input autoFocus value={search} onChange={(event) => onSearch(event.target.value)} placeholder={`Search ${meta.label.toLowerCase()}…`} /><button className="select-all" onClick={() => void onToggleAll(activeKind)}>{allEnabled ? 'Disable all' : 'Enable all'}</button></div><div className="capability-count">{selection[activeKind].length} of {catalog[activeKind].length} enabled for this session</div><div className="capability-list">{items.map((item) => <div className="capability-item" key={item.name}><button className="capability-detail-button" onClick={() => onInspect(activeKind, item.name)}><span className="capability-item-head"><strong>{humanize(item.name)}</strong><span className={`cap-tag cap-${item.source}`}>{item.source === 'extension' ? 'Extension' : 'Default'}</span>{item.evolving ? <span className="cap-tag cap-evolving">Evolving</span> : null}</span><small>{capabilityDescription(activeKind, item.name)}</small><em>Open {CAPABILITY_META[activeKind].label.slice(0, -1)} details →</em></button><button className={`toggle ${selection[activeKind].includes(item.name) ? 'enabled' : ''}`} onClick={() => void onToggle(activeKind, item.name)} aria-pressed={selection[activeKind].includes(item.name)} aria-label={`Toggle ${item.name}`}><span /></button></div>)}{!items.length ? <p className="empty">No {meta.label.toLowerCase()} match this search.</p> : null}</div></section></section></div>;
}

function CapabilityDetailDialog({ detail, loading, onEdit, onClose }: { detail?: CapabilityDetail; loading?: boolean; onEdit?: () => void; onClose: () => void }) {
  if (loading) return <div className="modal-backdrop detail-backdrop" onClick={onClose}><section className="capability-detail-dialog loading-detail" onClick={(event) => event.stopPropagation()}><span className="pulse" /> Loading capability details…</section></div>;
  if (!detail) return null;
  const meta = CAPABILITY_META[detail.kind];
  return <div className="modal-backdrop detail-backdrop" onClick={onClose}><section className="capability-detail-dialog" onClick={(event) => event.stopPropagation()}><header className="detail-header"><div><p className="eyebrow">{meta.label.slice(0, -1)} details</p><h2><CapIcon kind={detail.kind} size={20} /> {humanize(detail.name)}</h2><p>{detail.description || 'No description is available.'}</p></div><div className="detail-header-actions">{detail.editable ? <button className="edit-configuration" onClick={onEdit}>Edit configuration</button> : null}<button className="close-dialog" onClick={onClose}>×</button></div></header><div className="detail-layout"><aside className="detail-meta"><p className="eyebrow">Metadata</p><dl><dt>Version</dt><dd>{detail.version}</dd><dt>Permission</dt><dd>{detail.permission_mode}</dd><dt>Type</dt><dd>{Array.isArray(detail.type) ? detail.type.join(', ') : detail.type || '—'}</dd><dt>Evolvable</dt><dd>{detail.enable_evolving ? 'Yes' : 'No'}</dd>{detail.usage ? <><dt>Usage</dt><dd><code>{detail.usage}</code></dd></> : null}{detail.document_path ? <><dt>Source</dt><dd><code>{detail.document_path}</code></dd></> : null}</dl>{detail.actions.length ? <><p className="eyebrow detail-actions-heading">Actions</p><ul className="detail-actions">{detail.actions.map((action) => <li key={action}>{action}</li>)}</ul></> : null}</aside><article className="document-panel">{detail.language === 'markdown' ? <><div className="document-toolbar"><span>Capability guide</span><button onClick={() => navigator.clipboard?.writeText(detail.document)}>Copy</button></div><MarkdownDocument content={detail.document} /></> : detail.language === 'source' ? <WorkflowDocument detail={detail} /> : <SchemaPanel schema={detail.parameter_schema} />}</article></div></section></div>;
}

function CapabilityConfigDialog({ detail, onSave, onClose }: { detail: CapabilityDetail; onSave: (detail: CapabilityDetail, configuration: Record<string, unknown>) => Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState(() => JSON.stringify(detail.configuration, null, 2));
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const save = async () => {
    try {
      const parsed = JSON.parse(draft) as unknown;
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Configuration must be a JSON object.');
      setSaving(true);
      setError('');
      await onSave(detail, parsed as Record<string, unknown>);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };
  return <div className="modal-backdrop config-backdrop" onClick={onClose}><section className="config-dialog" onClick={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Runtime configuration</p><h2>Edit {humanize(detail.name)}</h2><p>Saving creates a new runtime version. Use valid JSON only.</p></div><button className="close-dialog" onClick={onClose}>×</button></header><textarea value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} aria-label="Capability configuration JSON" />{error ? <p className="config-error">{error}</p> : null}<footer><button className="secondary" onClick={onClose} disabled={saving}>Cancel</button><button onClick={() => void save()} disabled={saving}>{saving ? 'Saving…' : 'Save configuration'}</button></footer></section></div>;
}

function ModelsDialog({ providers, onAdd, onEdit, onClose }: { providers: ProviderSummary[]; onAdd: () => void; onEdit: (name: string) => void; onClose: () => void }) {
  const total = providers.reduce((count, provider) => count + provider.models.length, 0);
  return <div className="modal-backdrop models-backdrop" onClick={onClose}><section className="models-dialog" onClick={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Model catalog</p><h2>Providers & models</h2><p>{total} registered models across {providers.length} providers.</p></div><div className="detail-header-actions"><button className="edit-configuration" onClick={onAdd}>Add model</button><button className="close-dialog" onClick={onClose}>×</button></div></header><div className="provider-list">{providers.map((provider) => <section className="provider-group" key={provider.name}><h3>{humanize(provider.name)} <span>{provider.models.length}</span></h3><div>{provider.models.map((model) => <article className="model-row" key={model.name}><div><strong>{model.name}</strong><small>{model.id} · {model.type}</small></div><div className="model-row-actions"><div className="model-badges">{model.functions ? <span>Tools</span> : null}{model.vision ? <span>Vision</span> : null}{model.streaming ? <span>Stream</span> : null}</div><button className="edit-model" onClick={() => onEdit(model.name)}>Edit</button></div></article>)}</div></section>)}{!providers.length ? <p className="empty">No models are registered by the Gateway.</p> : null}</div></section></div>;
}

function ModelConfigDialog({ editor, onSave, onClose }: { editor: ModelEditorState; onSave: (editor: ModelEditorState, configuration: Record<string, unknown>, apiKey: string, clearApiKey: boolean) => Promise<void>; onClose: () => void }) {
  const [draft, setDraft] = useState(() => JSON.stringify(editor.configuration, null, 2));
  const [apiKey, setApiKey] = useState('');
  const [clearApiKey, setClearApiKey] = useState(false);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);
  const save = async () => {
    try {
      const parsed = JSON.parse(draft) as unknown;
      if (!isRecord(parsed)) throw new Error('Configuration must be a JSON object.');
      setSaving(true);
      setError('');
      await onSave(editor, parsed, apiKey, clearApiKey);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : String(reason));
    } finally {
      setSaving(false);
    }
  };
  const title = editor.originalName ? `Edit ${humanize(editor.originalName)}` : 'Add model';
  return <div className="modal-backdrop config-backdrop model-config-backdrop" onClick={onClose}><section className="config-dialog model-config-dialog" onClick={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Provider connection</p><h2>{title}</h2><p>Set the provider, model capabilities, and connection options. Changes apply immediately to this Gateway; API keys are write-only and never returned to the browser.</p></div><button className="close-dialog" onClick={onClose}>×</button></header><div className="model-credential"><label>API key <span>{editor.hasApiKey ? '(configured; leave blank to keep it)' : '(optional)'}</span><input type="password" value={apiKey} onChange={(event) => { setApiKey(event.target.value); setClearApiKey(false); }} placeholder={editor.hasApiKey ? 'Configured' : 'Provider key'} autoComplete="new-password" /></label>{editor.hasApiKey ? <label className="clear-key"><input type="checkbox" checked={clearApiKey} onChange={(event) => setClearApiKey(event.target.checked)} /> Clear the saved API key</label> : null}</div><textarea value={draft} onChange={(event) => setDraft(event.target.value)} spellCheck={false} aria-label="Model configuration JSON" />{error ? <p className="config-error">{error}</p> : null}<footer><button className="secondary" onClick={onClose} disabled={saving}>Cancel</button><button onClick={() => void save()} disabled={saving}>{saving ? 'Saving…' : 'Save model'}</button></footer></section></div>;
}

/** Render an image / audio / video / PDF workspace file from its data URL. */
function MediaDocument({ file, src }: { file: WorkspaceFile; src: string }) {
  const mime = file.mime_type;
  if (mime.startsWith('image/')) {
    return <div className="media-document"><img src={src} alt={file.name} /></div>;
  }
  if (mime.startsWith('video/')) {
    return <div className="media-document"><video src={src} controls preload="metadata" /></div>;
  }
  if (mime.startsWith('audio/')) {
    return <div className="media-document"><audio src={src} controls preload="metadata" /></div>;
  }
  return <div className="media-document media-document-embed"><iframe title={file.name} src={src} /></div>;
}

/** Inline live view of an environment (e.g. the browser over noVNC) in the conversation. */
function EnvironmentLive({ view, onClose }: { view: EnvironmentViewInfo; onClose: () => void }) {
  return (
    <section className="environment-live">
      <header>
        <span className="live-dot" />
        <strong>{view.label || 'Live environment'}</strong>
        <small>{view.env_name}</small>
        <button className="live-close" onClick={onClose} aria-label="Hide live view">×</button>
      </header>
      <div className="environment-live-body">
        {view.type === 'vnc'
          ? <Suspense fallback={<div className="vnc-overlay">Loading live view…</div>}><VncView url={view.url} password={view.password} /></Suspense>
          : <iframe title={view.label || 'Live environment'} src={view.url} />}
      </div>
    </section>
  );
}

function MarkdownDocument({ content }: { content: string }) {
  return <div className="markdown-document"><ReactMarkdown
    remarkPlugins={[remarkGfm]}
    rehypePlugins={MARKDOWN_REHYPE_PLUGINS}
    components={{ pre: ({ children }) => <CodeBlock>{children}</CodeBlock> }}
  >{content.replace(/^---\s*\n[\s\S]*?\n---\s*\n/, '')}</ReactMarkdown></div>;
}

function SchemaPanel({ schema }: { schema?: Record<string, unknown> }) {
  return <div className="schema-panel"><div className="document-toolbar"><span>Parameters</span>{schema ? <button onClick={() => navigator.clipboard?.writeText(JSON.stringify(schema, null, 2))}>Copy schema</button> : null}</div>{schema ? <pre className="source-document"><code>{JSON.stringify(schema, null, 2)}</code></pre> : <div className="schema-empty"><strong>No parameters required</strong><p>This capability does not expose a structured input schema.</p></div>}</div>;
}

function WorkflowDocument({ detail }: { detail: CapabilityDetail }) {
  const [view, setView] = useState<'preview' | 'source' | 'schema'>('preview');
  return <><div className="document-toolbar workflow-toolbar"><div className="document-tabs"><button className={view === 'preview' ? 'active' : ''} onClick={() => setView('preview')}>Preview</button><button className={view === 'source' ? 'active' : ''} onClick={() => setView('source')}>HTML</button><button className={view === 'schema' ? 'active' : ''} onClick={() => setView('schema')}>Inputs</button></div>{view === 'source' ? <button onClick={() => navigator.clipboard?.writeText(detail.document)}>Copy source</button> : null}</div>{view === 'preview' ? <iframe className="workflow-preview-frame" title={`${detail.name} workflow preview`} sandbox="allow-scripts" srcDoc={detail.preview_document ?? detail.document} /> : view === 'source' ? <pre className="source-document"><code>{detail.document}</code></pre> : <SchemaPanel schema={detail.parameter_schema} />}</>;
}

function ConnectionDialog({ endpoint, token, onEndpoint, onToken, onClose, onConnect }: { endpoint: string; token: string; onEndpoint: (value: string) => void; onToken: (value: string) => void; onClose: () => void; onConnect: () => void }) {
  return <div className="modal-backdrop"><section className="modal"><div className="modal-title"><h2>Gateway connection</h2><button onClick={onClose}>×</button></div><label>WebSocket endpoint<input value={endpoint} onChange={(event) => onEndpoint(event.target.value)} placeholder={DEFAULT_ENDPOINT} /></label><label>Token <span>(optional)</span><input value={token} onChange={(event) => onToken(event.target.value)} type="password" /></label><div className="modal-actions"><button className="secondary" onClick={onClose}>Cancel</button><button onClick={onConnect}>Connect</button></div></section></div>;
}

// Available capabilities: each entry may be an enriched object ({type, name,
// source, evolving}) or — for backward-compat — a bare name string.
function asCatalog(value: unknown): CapabilityCatalog {
  const source = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const itemsFor = (kind: CapabilityKind): CapabilityItem[] => (Array.isArray(source[kind]) ? source[kind] : [])
    .map((entry): CapabilityItem | null => {
      if (typeof entry === 'string') return { type: kind.slice(0, -1), name: entry, source: 'default', evolving: false };
      if (entry && typeof entry === 'object') {
        const e = entry as Record<string, unknown>;
        if (typeof e.name !== 'string') return null;
        return { type: typeof e.type === 'string' ? e.type : kind.slice(0, -1), name: e.name,
                 source: e.source === 'extension' ? 'extension' : 'default', evolving: Boolean(e.evolving) };
      }
      return null;
    })
    .filter((item): item is CapabilityItem => item !== null);
  return { agents: itemsFor('agents'), tools: itemsFor('tools'), skills: itemsFor('skills'), connectors: itemsFor('connectors'), environments: itemsFor('environments'), workflows: itemsFor('workflows'), commands: itemsFor('commands'), canvas: itemsFor('canvas') };
}

// Selected capabilities are tracked by name (strings or {name} objects).
function asSelection(value: unknown): CapabilitySelection {
  const source = value && typeof value === 'object' ? value as Record<string, unknown> : {};
  const namesFor = (kind: CapabilityKind) => (Array.isArray(source[kind]) ? source[kind] : [])
    .map((item) => (typeof item === 'string' ? item : (item && typeof item === 'object' && typeof (item as Record<string, unknown>).name === 'string' ? (item as Record<string, string>).name : null)))
    .filter((name): name is string => typeof name === 'string');
  return { agents: namesFor('agents'), tools: namesFor('tools'), skills: namesFor('skills'), connectors: namesFor('connectors'), environments: namesFor('environments'), workflows: namesFor('workflows'), commands: namesFor('commands'), canvas: namesFor('canvas') };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function asEnvironmentView(value: unknown): EnvironmentViewInfo | undefined {
  if (!isRecord(value) || typeof value.url !== 'string' || !value.url) return undefined;
  return {
    env_name: typeof value.env_name === 'string' ? value.env_name : 'environment',
    type: typeof value.type === 'string' ? value.type : 'vnc',
    url: resolveViewUrl(value.url),
    label: typeof value.label === 'string' ? value.label : undefined,
    password: typeof value.password === 'string' ? value.password : undefined,
  };
}

// The gateway hands out a relative path (e.g. "/env/vnc") for live views it
// relays. Resolve it against the page origin (the Vite proxy forwards it to the
// gateway) and carry the gateway token so the relay authorizes the socket.
// Absolute ws(s):// urls are passed through untouched.
function resolveViewUrl(url: string): string {
  if (/^wss?:\/\//i.test(url)) return url;
  const base = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}`;
  const tok = localStorage.getItem('autogenesis.gateway.token') ?? '';
  const query = tok ? `?token=${encodeURIComponent(tok)}` : '';
  return `${base}${url.startsWith('/') ? '' : '/'}${url}${query}`;
}

function asDeploySite(value: unknown): DeploySite | undefined {
  if (!isRecord(value) || typeof value.site_id !== 'string') return undefined;
  return {
    site_id: value.site_id,
    runtime: typeof value.runtime === 'string' ? value.runtime : 'unknown',
    status: typeof value.status === 'string' ? value.status : 'detached',
    url: typeof value.url === 'string' ? value.url : undefined,
    port: typeof value.port === 'number' ? value.port : undefined,
  };
}

function asCapabilityDetail(value: Record<string, unknown>): CapabilityDetail {
  const kind = CAPABILITY_KINDS.includes(value.kind as CapabilityKind) ? value.kind as CapabilityKind : 'skills';
  return {
    kind,
    name: String(value.name ?? ''),
    description: String(value.description ?? ''),
    version: String(value.version ?? '1.0.0'),
    permission_mode: String(value.permission_mode ?? 'workspace_write'),
    type: typeof value.type === 'string' || Array.isArray(value.type) ? value.type as string | string[] : undefined,
    enable_evolving: Boolean(value.enable_evolving),
    actions: Array.isArray(value.actions) ? value.actions.filter((item): item is string => typeof item === 'string') : [],
    parameter_schema: value.parameter_schema && typeof value.parameter_schema === 'object' && !Array.isArray(value.parameter_schema) ? value.parameter_schema as Record<string, unknown> : undefined,
    usage: typeof value.usage === 'string' ? value.usage : undefined,
    configuration: value.configuration && typeof value.configuration === 'object' && !Array.isArray(value.configuration) ? value.configuration as Record<string, unknown> : {},
    editable: Boolean(value.editable),
    document: String(value.document ?? ''),
    preview_document: typeof value.preview_document === 'string' ? value.preview_document : undefined,
    document_path: typeof value.document_path === 'string' ? value.document_path : undefined,
    language: value.language === 'schema' ? 'schema' : value.language === 'html' || value.language === 'source' ? 'source' : 'markdown',
  };
}

function isProviderSummary(value: unknown): value is ProviderSummary {
  return Boolean(value)
    && typeof value === 'object'
    && typeof (value as { name?: unknown }).name === 'string'
    && Array.isArray((value as { models?: unknown }).models);
}

function asUploadedAttachment(value: unknown): UploadedAttachment | undefined {
  if (!isRecord(value) || typeof value.id !== 'string' || typeof value.name !== 'string' || typeof value.path !== 'string' || typeof value.size !== 'number') return undefined;
  return {
    id: value.id,
    name: value.name,
    path: value.path,
    size: value.size,
    mimeType: typeof value.mime_type === 'string' ? value.mime_type : 'application/octet-stream',
    status: 'ready',
    progress: value.size,
  };
}

function isSessionSummary(value: unknown): value is SessionSummary {
  return Boolean(value)
    && typeof value === 'object'
    && typeof (value as { session_id?: unknown }).session_id === 'string'
    && typeof (value as { workspace?: unknown }).workspace === 'string'
    && ((value as { source_workspace?: unknown }).source_workspace === undefined
      || (value as { source_workspace?: unknown }).source_workspace === null
      || typeof (value as { source_workspace?: unknown }).source_workspace === 'string')
    && typeof (value as { name?: unknown }).name === 'string'
    && Array.isArray((value as { task_ids?: unknown }).task_ids);
}

function isWorkspaceEntry(value: unknown): value is WorkspaceEntry {
  return isRecord(value)
    && typeof value.name === 'string'
    && typeof value.path === 'string'
    && (value.type === 'directory' || value.type === 'file')
    && typeof value.modified_at === 'number';
}

function asWorkspaceFile(value: unknown): WorkspaceFile | undefined {
  if (!isRecord(value)
    || typeof value.name !== 'string'
    || typeof value.path !== 'string'
    || typeof value.content !== 'string'
    || typeof value.size !== 'number'
    || typeof value.modified_at !== 'number'
    || typeof value.etag !== 'string'
    || typeof value.mime_type !== 'string'
    || typeof value.language !== 'string') return undefined;
  // `encoding` is optional for compatibility with older gateways (text-only).
  if (value.encoding !== undefined && typeof value.encoding !== 'string') return undefined;
  return value as unknown as WorkspaceFile;
}

/** Media files arrive base64-encoded; render them straight from a data URL. */
function mediaSource(file: WorkspaceFile): string | undefined {
  if (file.encoding !== 'base64') return undefined;
  return `data:${file.mime_type};base64,${file.content}`;
}

function isGenericSessionName(name: string): boolean { return name === 'web' || name === 'interactive' || name.startsWith('Web session '); }
function makeSessionTitle(content: string): string { return content.replace(/\s+/g, ' ').trim().slice(0, 72); }

function activityStep(event: GatewayEvent): ActivityStep {
  if (event.type === 'task.submitted') return { id: `${event.seq_no}:queued`, title: 'Task queued', content: String(event.payload.content ?? ''), timestamp: event.timestamp };
  if (event.type === 'task.started') return { id: `${event.seq_no}:started`, title: 'Meta agent started', content: 'Preparing the task and selecting capabilities.', timestamp: event.timestamp, running: true };
  const trace = event.payload;
  const type = String(trace.event_type ?? 'event').replaceAll('_', ' ');
  const actor = String(trace.action_name ?? trace.agent_name ?? trace.label ?? 'Agent');
  return { id: `${event.seq_no}:${type}`, title: `${actor} · ${type}`, content: traceSummary(trace), detail: JSON.stringify(trace, null, 2), trace, timestamp: event.timestamp, running: type.endsWith('start') };
}

function traceSummary(trace: Record<string, unknown>): string | undefined {
  const type = String(trace.event_type ?? '');
  if (type === 'agent_call') {
    const reasoning = traceReasoning(trace);
    return reasoning ? reasoning.replace(/[*_`#]/g, '').replace(/\s+/g, ' ').trim() : 'Reasoning completed';
  }
  if (type.endsWith('_start') && isRecord(trace.input)) {
    const command = trace.input.command ?? trace.input.cmd ?? trace.input.script;
    if (typeof command === 'string') return command.split('\n')[0];
    const keys = Object.keys(trace.input);
    return keys.length ? `${keys.length} argument${keys.length === 1 ? '' : 's'}: ${keys.slice(0, 3).join(', ')}` : 'No arguments';
  }
  if (trace.error) return String(trace.error);
  if (typeof trace.output === 'string') return trace.output.replace(/\s+/g, ' ').trim();
  if (trace.output !== undefined && trace.output !== null) return 'Structured output available';
  if (trace.success === true) return typeof trace.duration_ms === 'number' ? `Completed in ${formatDuration(trace.duration_ms)}` : 'Completed successfully';
  return typeof trace.label === 'string' ? trace.label : undefined;
}

function finalMessage(event: GatewayEvent, type: Extract<MessageType, 'assistant' | 'error' | 'system'>): Message {
  if (type === 'assistant') return { id: `${event.task_id}:final`, type, title: 'Autogenesis', content: String(event.payload.message ?? event.payload.result ?? 'Task completed'), detail: JSON.stringify(event.payload, null, 2), timestamp: event.timestamp };
  if (type === 'error') return { id: `${event.task_id}:error`, type, title: 'Task failed', content: String(event.payload.error ?? 'Unknown error'), detail: JSON.stringify(event.payload, null, 2), timestamp: event.timestamp };
  return { id: `${event.task_id}:cancelled`, type, title: 'Task cancelled', timestamp: event.timestamp };
}

function formatTime(timestamp: string): string { return new Date(timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
function formatFileSize(size: number): string { if (size < 1024) return `${size} B`; if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`; if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`; return `${(size / 1024 ** 3).toFixed(2)} GB`; }
function fileName(path: string): string { return path.split(/[\\/]/).at(-1) || path; }
function base64FromBuffer(buffer: ArrayBuffer): string { const bytes = new Uint8Array(buffer); let binary = ''; for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000)); return btoa(binary); }
function humanize(name: string): string { return name.replace(/_skill$|_tool$|_agent$|_connector$|_workflow$/, '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase()); }
function capabilityDescription(kind: CapabilityKind, name: string): string { return kind === 'commands' ? `Run /${name} from the composer when this command is enabled.` : `${humanize(name)} ${kind.slice(0, -1)} is ${kind === 'agents' ? 'available for delegation' : 'available to this session'}.`; }
