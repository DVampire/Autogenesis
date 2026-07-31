import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { ArrowUp, Bot, Check, ChevronDown, Copy, Eraser, FileText, Loader2, MessagesSquare, PanelLeft, Paperclip, Pencil, Plus, Sparkles, Square, ThumbsDown, ThumbsUp, Trash2, User, X } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

import { Button } from '../components/ui/button';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { Textarea } from '../components/ui/textarea';
import { cn } from '../utils/utils';
import type { GatewayEvent } from '../controllers/gateway';
import type { FrameDoc, RequestFn, RunData } from './types';

// Langflow-style playground: opened from the canvas, its chat drives the
// CURRENT flow (each message = one run on the workflow runtime, with the
// execution record attached to the reply). A second tab chats directly with
// model_manager for quick LLM debugging.
//
// Structure/markup is copied from Langflow's IOModal chatView + the newer
// playgroundComponent chat-input: a centered max-w-[768px] column, a bordered
// focus-reactive composer card with an auto-resizing textarea over a toolbar
// row, an ArrowUp send button, per-message avatar rows with a hover copy bar,
// and a branded "New chat" empty state.

interface FlowInputField { name: string; input_type: string; required: boolean; default: string; }
interface ExecutionStep { step: string; state: string; duration: string; }
interface FlowMessage { role: 'user' | 'assistant'; content: string; failed?: boolean; execution?: ExecutionStep[]; duration?: string; }
interface ModelMessage { role: 'user' | 'assistant'; content: string; }

const PREFERRED_INPUT_NAMES = ['message', 'input', 'question', 'task', 'query', 'prompt', 'text'];
const MODEL_KEY = 'autogenesis.playground.model';

// Langflow chat-input auto-resize bounds (constants/constants.ts).
const CHAT_INPUT_MIN_HEIGHT = 24;
const CHAT_INPUT_MAX_HEIGHT = 200;

// Copied from Langflow's text-area-wrapper.tsx resizeTextarea.
function resizeTextarea(textarea: HTMLTextAreaElement, value: string): void {
  textarea.style.height = '0px';
  const scrollHeight = textarea.scrollHeight;
  if (!value || value.trim() === '') {
    textarea.style.height = `${CHAT_INPUT_MIN_HEIGHT}px`;
    textarea.style.overflowY = 'hidden';
  } else {
    const newHeight = Math.max(CHAT_INPUT_MIN_HEIGHT, Math.min(scrollHeight, CHAT_INPUT_MAX_HEIGHT));
    textarea.style.height = `${newHeight}px`;
    textarea.style.overflowY = scrollHeight > CHAT_INPUT_MAX_HEIGHT ? 'auto' : 'hidden';
  }
}

function frameDuration(frame: { started_at?: string | null; finished_at?: string | null }): string {
  if (!frame.started_at || !frame.finished_at) return '';
  const ms = new Date(frame.finished_at).getTime() - new Date(frame.started_at).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '';
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
}

// Wall duration across a run's frames (min start → max finish), for the
// "Finished in Xs" metadata line.
function runWallDuration(frames: Record<string, FrameDoc>): string {
  let start = Infinity;
  let finish = -Infinity;
  for (const frame of Object.values(frames)) {
    if (frame.started_at) start = Math.min(start, new Date(frame.started_at).getTime());
    if (frame.finished_at) finish = Math.max(finish, new Date(frame.finished_at).getTime());
  }
  if (!Number.isFinite(start) || !Number.isFinite(finish) || finish < start) return '';
  const ms = finish - start;
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(2)} s`;
}

// Turn a flow's structured output into the chat reply text. Agent/Chat-Output
// nodes emit shapes like { answer: { message, data: { result, reasoning }, files } }
// or { result: "…" }; the chat should show the natural-language reply, not the
// raw JSON (which stays visible in the run-output panel). We look for a text
// field, dig into a nested `data`, and unwrap single-key envelopes recursively;
// only truly unknown multi-field objects fall back to pretty JSON.
const REPLY_KEYS = ['message', 'result', 'text', 'content', 'answer', 'output', 'response', 'reply'];
function formatOutputs(output: unknown, depth = 0): string {
  if (output === null || output === undefined) return '(no output)';
  if (typeof output === 'string') return output;
  if (typeof output !== 'object') return String(output);
  if (Array.isArray(output)) return JSON.stringify(output, null, 2);
  const obj = output as Record<string, unknown>;
  for (const key of REPLY_KEYS) {
    if (typeof obj[key] === 'string' && (obj[key] as string).trim()) return obj[key] as string;
  }
  if (obj.data && typeof obj.data === 'object' && !Array.isArray(obj.data)) {
    for (const key of REPLY_KEYS) {
      const value = (obj.data as Record<string, unknown>)[key];
      if (typeof value === 'string' && value.trim()) return value;
    }
  }
  const entries = Object.entries(obj);
  if (entries.length === 1 && depth < 4) return formatOutputs(entries[0][1], depth + 1);
  return JSON.stringify(output, null, 2);
}

// Langflow message-options.tsx: the floating bordered action bar — an optional
// edit (pencil) for user messages, plus copy with a copied-state check.
function MessageActions({ copyText, onEdit, onFeedback }: { copyText?: string; onEdit?: () => void; onFeedback?: (value: 1 | -1) => void }) {
  const [copied, setCopied] = useState(false);
  const [vote, setVote] = useState<1 | -1 | 0>(0);
  if (!copyText && !onEdit && !onFeedback) return null;
  return (
    <div className="flex items-center rounded-md border border-border bg-background">
      {onEdit ? (
        <div className="p-1">
          <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Edit message" onClick={onEdit}>
            <Pencil className="h-4 w-4" />
          </Button>
        </div>
      ) : null}
      {onFeedback ? (
        <>
          <div className="p-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Helpful"
              onClick={() => { setVote((current) => (current === 1 ? 0 : 1)); onFeedback(1); }}>
              <ThumbsUp className={cn('h-4 w-4', vote === 1 && 'text-accent-emerald-foreground')} />
            </Button>
          </div>
          <div className="p-1">
            <Button variant="ghost" size="icon" className="h-8 w-8" aria-label="Not helpful"
              onClick={() => { setVote((current) => (current === -1 ? 0 : -1)); onFeedback(-1); }}>
              <ThumbsDown className={cn('h-4 w-4', vote === -1 && 'text-destructive')} />
            </Button>
          </div>
        </>
      ) : null}
      {copyText ? (
        <div className="p-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            aria-label={copied ? 'Copied' : 'Copy message'}
            onClick={() => { void navigator.clipboard.writeText(copyText); setCopied(true); setTimeout(() => setCopied(false), 2000); }}
          >
            {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          </Button>
        </div>
      ) : null}
    </div>
  );
}

// Langflow chatMessage/chat-message.tsx row: a full-width row with a 32px
// avatar, sender name (+ inline metadata), then the message content — not
// left/right bubbles. A hover copy bar floats above the row.
function Bubble({ role, failed, senderName, metadata, copyText, onEdit, onFeedback, children }: {
  role: 'user' | 'assistant';
  failed?: boolean;
  senderName: string;
  metadata?: React.ReactNode;
  copyText?: string;
  onEdit?: () => void;
  onFeedback?: (value: 1 | -1) => void;
  children: React.ReactNode;
}) {
  const isUser = role === 'user';
  return (
    <div className="w-full py-4 word-break-break-word">
      <div className="group relative flex w-full gap-4 rounded-md p-2 hover:bg-muted">
        {(copyText || onEdit || onFeedback) ? (
          <div className="invisible absolute bottom-full right-0 group-hover:visible">
            <MessageActions copyText={copyText} onEdit={onEdit} onFeedback={onFeedback} />
          </div>
        ) : null}
        <div className={cn(
          'relative flex h-[32px] w-[32px] items-center justify-center overflow-hidden rounded-md text-2xl',
          isUser ? 'border border-border hover:border-input' : 'bg-muted',
        )}>
          <div className="flex h-[18px] w-[18px] items-center justify-center">
            {isUser ? <User className="h-[18px] w-[18px]" /> : <Bot className="h-[18px] w-[18px]" />}
          </div>
        </div>
        <div className="flex w-[94%] flex-col">
          <div className="flex w-full items-baseline gap-3 pb-2 text-sm font-semibold">
            <span className="flex items-center gap-2">{senderName}</span>
            {metadata}
          </div>
          <div className={cn('playground-markdown min-w-0 text-sm leading-relaxed', failed ? 'text-destructive' : 'text-foreground')}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );
}

// Session sidebar — Langflow's IOModal sidebar-open-view: a per-conversation
// list (title from the first user message) with switch + delete.
function SessionSidebar({ sessions, activeId, onSwitch, onDelete }: {
  sessions: Array<{ session_id: string; title?: string; message_count?: number }>;
  activeId: string;
  onSwitch: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  return (
    <div className="flex w-[184px] shrink-0 flex-col overflow-y-auto border-r border-border bg-muted/40 p-2 custom-scroll">
      <div className="flex items-center gap-2 px-1 pb-2 pt-1">
        <MessagesSquare className="h-[18px] w-[18px] text-muted-foreground" />
        <span className="text-sm font-medium">Chats</span>
      </div>
      {sessions.length === 0 ? <p className="px-1 text-xs text-muted-foreground">No saved chats yet.</p> : null}
      {sessions.map((session) => (
        <div
          key={session.session_id}
          onClick={() => onSwitch(session.session_id)}
          className={cn('group flex cursor-pointer items-center gap-1 rounded-md px-2 py-1.5 text-sm hover:bg-muted', session.session_id === activeId && 'bg-muted font-medium')}
        >
          <span className="flex-1 truncate">{session.title || 'Untitled'}</span>
          <button
            type="button"
            onClick={(event) => { event.stopPropagation(); onDelete(session.session_id); }}
            className="text-muted-foreground opacity-0 transition-all hover:text-destructive group-hover:opacity-100"
            aria-label="Delete chat"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </button>
        </div>
      ))}
    </div>
  );
}

// Langflow chat-view.tsx branded empty state (LangflowLogo → our brand glyph).
function EmptyState({ subtitle, hint }: { subtitle: string; hint?: React.ReactNode }) {
  return (
    <div className="flex flex-grow w-full flex-col items-center justify-center">
      <div className="flex flex-col items-center justify-center gap-4 p-8">
        <Sparkles className="h-10 w-10 scale-[1.5] text-primary" aria-hidden="true" />
        <div className="flex flex-col items-center justify-center">
          <h3 className="mt-2 pb-2 text-2xl font-semibold text-primary">New chat</h3>
          <p className="text-lg text-muted-foreground">{subtitle}</p>
          {hint ? <p className="mt-1 text-center text-xs text-muted-foreground">{hint}</p> : null}
        </div>
      </div>
    </div>
  );
}

export function PlaygroundPanel({ request, subscribe, sessionId, connected, onNotice, onClose, inputNodes, startRun, stopRun, runId, runData, runOutput, runError }: {
  request: RequestFn;
  subscribe: (listener: (event: GatewayEvent) => void) => () => void;
  sessionId?: string;
  connected: boolean;
  onNotice: (message: string) => void;
  onClose: () => void;
  inputNodes: FlowInputField[];
  startRun: (input: Record<string, unknown>) => Promise<string | undefined>;
  stopRun?: () => void;
  runId?: string;
  runData?: RunData;
  runOutput?: unknown;
  runError?: string;
}) {
  const [tab, setTab] = useState<'flow' | 'model'>('flow');
  const [flowMessages, setFlowMessages] = useState<FlowMessage[]>([]);
  const [flowInput, setFlowInput] = useState('');
  const [pendingRun, setPendingRun] = useState<string>();
  const endRef = useRef<HTMLDivElement>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  // Stick-to-bottom: only auto-scroll when the user is already near the bottom
  // (Langflow's use-stick-to-bottom behavior — don't yank them down mid-scroll).
  const [atBottom, setAtBottom] = useState(true);
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (el) setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 80);
  }, []);

  // ----- persistent chat sessions (flow tab): sidebar list + switching ------
  // The chat-record id is client-managed (decoupled from the WS session) so we
  // can hold several conversations under one connection; the sidebar reads
  // output/<owner>/sessions via the chat.* gateway commands.
  const [chatSessionId, setChatSessionId] = useState<string>(() => `c${Math.random().toString(36).slice(2, 10)}`);
  const [sessions, setSessions] = useState<Array<{ session_id: string; title?: string; updated_at?: string; message_count?: number }>>([]);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const persistFlow = useCallback((role: 'user' | 'assistant', content: string) => {
    void request('chat.append', { session_id: chatSessionId, role, content, tab: 'flow' });
  }, [request, chatSessionId]);

  const loadSessions = useCallback(async () => {
    const response = await request('chat.sessions.list');
    if (response.ok && Array.isArray(response.result.sessions)) setSessions(response.result.sessions as typeof sessions);
  }, [request]);

  const switchSession = useCallback(async (id: string) => {
    const response = await request('chat.session.load', { session_id: id });
    const messages = response.ok && Array.isArray(response.result.messages) ? response.result.messages as Array<{ role: string; content: unknown }> : [];
    setFlowMessages(messages.map((message) => ({ role: message.role === 'user' ? 'user' : 'assistant', content: String(message.content ?? '') })));
    setChatSessionId(id);
    setTab('flow');
  }, [request]);

  const newSession = useCallback(() => { setChatSessionId(`c${Math.random().toString(36).slice(2, 10)}`); setFlowMessages([]); setTab('flow'); }, []);

  const deleteSession = useCallback(async (id: string) => {
    await request('chat.session.delete', { session_id: id });
    if (id === chatSessionId) newSession();
    void loadSessions();
  }, [request, chatSessionId, newSession, loadSessions]);

  useEffect(() => { if (sidebarOpen) void loadSessions(); }, [sidebarOpen, loadSessions]);

  // Reopen where the last conversation left off. The id above is generated
  // fresh on every mount, so without this each visit started a brand-new
  // conversation and the previous transcript — written to
  // output/<owner>/sessions/<id>/chat.jsonl — was never read back by anything.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const response = await request('chat.sessions.list');
      if (cancelled || !response.ok || !Array.isArray(response.result.sessions)) return;
      const list = response.result.sessions as typeof sessions;
      setSessions(list);
      const latest = list[0];  // the gateway returns them newest first
      if (latest?.session_id) await switchSession(latest.session_id);
    })();
    return () => { cancelled = true; };
  }, [request, switchSession]);

  // ----- file attachments (Langflow upload/drag/preview) --------------------
  // Chunked base64 upload via the file.upload.* commands (uploads land in the
  // owner's durable state/files); attached paths ride along on the next run.
  const [attached, setAttached] = useState<Array<{ id: string; name: string; path: string }>>([]);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const uploadFiles = useCallback(async (files: FileList | File[]) => {
    const list = Array.from(files);
    if (!sessionId || !list.length) return;
    setUploading(true);
    const CHUNK = 512 * 1024;
    const toB64 = (bytes: Uint8Array) => { let binary = ''; for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000)); return btoa(binary); };
    try {
      for (const file of list) {
        const begin = await request('file.upload.begin', { session_id: sessionId, name: file.name, size: file.size, mime_type: file.type || 'application/octet-stream' });
        if (!begin.ok) { onNotice(begin.error?.message ?? 'Upload failed'); continue; }
        const meta = begin.result.file as { id: string; path: string };
        const bytes = new Uint8Array(await file.arrayBuffer());
        let ok = true;
        for (let offset = 0; offset < bytes.length; offset += CHUNK) {
          const resp = await request('file.upload.chunk', { session_id: sessionId, file_id: meta.id, data: toB64(bytes.subarray(offset, offset + CHUNK)) });
          if (!resp.ok) { onNotice('Upload chunk failed'); ok = false; break; }
        }
        if (!ok) continue;
        const done = await request('file.upload.complete', { session_id: sessionId, file_id: meta.id });
        if (done.ok) setAttached((current) => [...current, { id: meta.id, name: file.name, path: (done.result.file as { path: string }).path }]);
      }
    } finally { setUploading(false); }
  }, [sessionId, request, onNotice]);

  const removeAttached = useCallback((id: string) => {
    setAttached((current) => current.filter((file) => file.id !== id));
    if (sessionId) void request('file.remove', { session_id: sessionId, file_id: id });
  }, [sessionId, request]);

  // ----- flow chat: input mapping ------------------------------------------
  const targetInput = useMemo(() => {
    const strings = inputNodes.filter((field) => field.input_type === 'string');
    return strings.find((field) => PREFERRED_INPUT_NAMES.includes(field.name.toLowerCase())) ?? strings[0];
  }, [inputNodes]);

  const sendFlow = useCallback(async () => {
    const content = flowInput.trim();
    if (!content || pendingRun || runId) return;
    const input: Record<string, unknown> = {};
    for (const field of inputNodes) {
      if (targetInput && field.name === targetInput.name) input[field.name] = content;
      else if (field.default) {
        try { input[field.name] = ['array', 'object', 'number', 'boolean'].includes(field.input_type) ? JSON.parse(field.default) : field.default; }
        catch { input[field.name] = field.default; }
      }
    }
    if (attached.length) input.files = attached.map((file) => file.path);
    setFlowMessages((current) => [...current, { role: 'user', content }]);
    persistFlow('user', content);
    setFlowInput('');
    setAttached([]);
    const rid = await startRun(input);
    if (!rid) {
      setFlowMessages((current) => [...current, { role: 'assistant', content: 'The flow could not start — check the notice.', failed: true }]);
      return;
    }
    setPendingRun(rid);
  }, [flowInput, pendingRun, runId, inputNodes, targetInput, startRun, persistFlow, attached]);

  // Run a flow that has no Chat Input directly (Langflow's no-input.tsx).
  const runFlowNoInput = useCallback(async () => {
    if (pendingRun || runId) return;
    const input: Record<string, unknown> = {};
    for (const field of inputNodes) {
      if (field.default) {
        try { input[field.name] = ['array', 'object', 'number', 'boolean'].includes(field.input_type) ? JSON.parse(field.default) : field.default; }
        catch { input[field.name] = field.default; }
      }
    }
    const rid = await startRun(input);
    if (!rid) {
      setFlowMessages((current) => [...current, { role: 'assistant', content: 'The flow could not start — check the notice.', failed: true }]);
      return;
    }
    setPendingRun(rid);
  }, [pendingRun, runId, inputNodes, startRun]);

  // When the watched run settles, turn its outputs + frames into a reply.
  useEffect(() => {
    if (!pendingRun || runId) return;
    const frames = runData?.frames ?? {};
    const execution: ExecutionStep[] = Object.values(frames).map((frame: FrameDoc) => ({
      step: frame.step_id + (frame.item_index != null ? `[${frame.item_index}]` : '') + (frame.iteration != null ? ` r${frame.iteration}` : ''),
      state: frame.state,
      duration: frameDuration(frame),
    }));
    const duration = runWallDuration(frames);
    const replyContent = runError ? runError : formatOutputs(runOutput);
    setFlowMessages((current) => [...current, runError
      ? { role: 'assistant', content: runError, failed: true, execution }
      : { role: 'assistant', content: replyContent, execution, duration }]);
    persistFlow('assistant', replyContent);
    setPendingRun(undefined);
  }, [pendingRun, runId, runData, runOutput, runError, persistFlow]);

  // ----- model chat (direct model_manager) ----------------------------------
  const [models, setModels] = useState<string[]>([]);
  const [model, setModel] = useState(() => localStorage.getItem(MODEL_KEY) ?? '');
  const [modelMessages, setModelMessages] = useState<ModelMessage[]>([]);
  const [modelInput, setModelInput] = useState('');
  const [streaming, setStreaming] = useState('');
  const [chatRequestId, setChatRequestId] = useState<string>();
  const chatRequestRef = useRef<string>();
  const streamRef = useRef('');
  chatRequestRef.current = chatRequestId;

  useEffect(() => { if (model) localStorage.setItem(MODEL_KEY, model); }, [model]);
  useEffect(() => { if (atBottom) endRef.current?.scrollIntoView({ behavior: 'smooth' }); }, [flowMessages, modelMessages, streaming, tab, pendingRun, atBottom]);

  // Auto-resize the composer textarea on value / tab change (Langflow parity).
  const currentValue = tab === 'flow' ? flowInput : modelInput;
  useEffect(() => { if (inputRef.current) resizeTextarea(inputRef.current, currentValue); }, [currentValue, tab]);

  useEffect(() => {
    if (!connected || tab !== 'model' || models.length) return;
    void (async () => {
      const response = await request('model.list');
      if (response.ok && Array.isArray(response.result.providers)) {
        const names = (response.result.providers as Array<{ models: Array<{ name: string }> }>).flatMap((provider) => provider.models.map((item) => item.name));
        setModels(names);
        if (names.length && !names.includes(model)) setModel(names[0]);
      }
    })().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connected, tab, request]);

  useEffect(() => {
    if (!connected) return;
    return subscribe((event) => {
      const payload = event.payload as Record<string, unknown>;
      if (!event.type.startsWith('model.chat.') || payload.request_id !== chatRequestRef.current) return;
      if (event.type === 'model.chat.delta' && typeof payload.text === 'string') {
        streamRef.current += payload.text;
        setStreaming(streamRef.current);
      } else if (event.type === 'model.chat.done') {
        const finalText = typeof payload.message === 'string' && payload.message ? payload.message : streamRef.current;
        setModelMessages((current) => [...current, { role: 'assistant', content: finalText }]);
        streamRef.current = ''; setStreaming(''); setChatRequestId(undefined);
      } else if (event.type === 'model.chat.cancelled') {
        if (streamRef.current) setModelMessages((current) => [...current, { role: 'assistant', content: streamRef.current }]);
        streamRef.current = ''; setStreaming(''); setChatRequestId(undefined);
      } else if (event.type === 'model.chat.error') {
        onNotice(String(payload.error ?? 'Model call failed'));
        streamRef.current = ''; setStreaming(''); setChatRequestId(undefined);
      }
    });
  }, [connected, subscribe, onNotice]);

  const sendModel = useCallback(async () => {
    const content = modelInput.trim();
    if (!content || !sessionId || !model || chatRequestId) return;
    const history = [...modelMessages, { role: 'user' as const, content }];
    setModelMessages(history);
    setModelInput('');
    streamRef.current = ''; setStreaming('');
    const response = await request('model.chat', { session_id: sessionId, model, messages: history });
    if (!response.ok || typeof response.result.request_id !== 'string') {
      onNotice(response.error?.message ?? 'Could not start the chat');
      return;
    }
    setChatRequestId(response.result.request_id);
  }, [modelInput, sessionId, model, chatRequestId, modelMessages, request, onNotice]);

  const flowBusy = Boolean(pendingRun || runId);
  const busy = tab === 'flow' ? flowBusy : Boolean(chatRequestId);
  const value = tab === 'flow' ? flowInput : modelInput;
  const inputDisabled = !connected || (tab === 'model' && !model);
  const canSend = tab === 'flow' ? Boolean(flowInput.trim()) && !flowBusy : Boolean(model && modelInput.trim());

  const onSend = () => void (tab === 'flow' ? sendFlow() : sendModel());
  const onStop = () => {
    if (tab === 'model' && chatRequestId) void request('model.chat.cancel', { request_id: chatRequestId });
    else if (tab === 'flow' && flowBusy) stopRun?.();
  };

  const placeholder = tab === 'flow'
    ? 'Send a message...'
    : model ? `Message ${model}…` : 'Select a model first';

  const hasFlow = flowMessages.length > 0 || flowBusy;
  const hasModel = modelMessages.length > 0 || Boolean(streaming) || Boolean(chatRequestId);

  return (
    <aside className="node-panel playground-panel nodrag nowheel">
      <header className="node-panel-head items-center">
        <div className="flex items-center gap-1.5">
          {tab === 'flow' ? (
            <>
              <Button variant={sidebarOpen ? 'ghostActive' : 'ghost'} size="iconSm" onClick={() => setSidebarOpen((open) => !open)} title="Chats" aria-label="Toggle chats"><PanelLeft /></Button>
              <Button variant="ghost" size="iconSm" onClick={newSession} title="New chat" aria-label="New chat"><Plus /></Button>
            </>
          ) : null}
          <Button variant={tab === 'flow' ? 'ghostActive' : 'ghost'} size="xs" onClick={() => setTab('flow')}>Flow</Button>
          <Button variant={tab === 'model' ? 'ghostActive' : 'ghost'} size="xs" onClick={() => setTab('model')}>Model</Button>
        </div>
        {tab === 'model' ? (
          <Select value={model || undefined} onValueChange={setModel}>
            <SelectTrigger className="ml-2 h-7 w-[190px] text-xs"><SelectValue placeholder="model…" /></SelectTrigger>
            <SelectContent className="max-h-72">{models.map((name) => <SelectItem key={name} value={name} className="text-xs">{name}</SelectItem>)}</SelectContent>
          </Select>
        ) : (
          <span className="ml-2 truncate text-xs text-muted-foreground">
            {targetInput ? `message → \${inputs.${targetInput.name}}` : 'runs the current flow'}
          </span>
        )}
        <Button variant="ghost" size="iconSm" className="ml-auto shrink-0" onClick={() => {
          if (tab === 'flow') setFlowMessages([]);
          else { setModelMessages([]); streamRef.current = ''; setStreaming(''); }
        }} title="Clear conversation"><Eraser /></Button>
        <Button variant="ghost" size="iconSm" className="shrink-0" onClick={onClose} aria-label="Close playground"><X /></Button>
      </header>

      <div className="flex min-h-0 flex-1">
        {sidebarOpen && tab === 'flow' ? (
          <SessionSidebar sessions={sessions} activeId={chatSessionId} onSwitch={(id) => void switchSession(id)} onDelete={(id) => void deleteSession(id)} />
        ) : null}
        <div className="flex min-h-0 flex-1 flex-col">
      {/* Transcript — centered max-w-[768px] column (Langflow chat-view.tsx) */}
      <div ref={scrollRef} onScroll={onScroll} className="relative flex min-h-0 flex-1 flex-col overflow-y-auto px-4">
        {!atBottom ? (
          <button
            type="button"
            onClick={() => { endRef.current?.scrollIntoView({ behavior: 'smooth' }); setAtBottom(true); }}
            className="absolute bottom-3 left-1/2 z-10 flex h-8 w-8 -translate-x-1/2 items-center justify-center rounded-full border border-border bg-background text-muted-foreground shadow-md hover:text-foreground"
            aria-label="Scroll to bottom"
          >
            <ChevronDown className="h-4 w-4" />
          </button>
        ) : null}
        <div className="mx-auto flex w-5/6 max-w-[768px] flex-grow flex-col">
          {tab === 'flow' ? (
            hasFlow ? <>
              {flowMessages.map((message, index) => (
                <Bubble
                  key={index}
                  role={message.role}
                  failed={message.failed}
                  senderName={message.role === 'user' ? 'User' : 'AI'}
                  copyText={message.content}
                  onEdit={message.role === 'user' && !flowBusy ? () => { setFlowInput(message.content); setFlowMessages((current) => current.slice(0, index)); inputRef.current?.focus(); } : undefined}
                  onFeedback={message.role === 'assistant' && sessionId ? (value) => { void request('chat.feedback', { session_id: sessionId, message_id: `flow-${index}`, value }); } : undefined}
                  metadata={message.role === 'assistant' && message.duration ? (
                    <span className="flex items-center gap-1.5 text-sm font-normal text-muted-foreground">
                      <Check className="h-4 w-4 text-accent-emerald-foreground" />
                      Finished in {message.duration}
                    </span>
                  ) : undefined}
                >
                  {message.role === 'user'
                    ? <span className="whitespace-pre-wrap">{message.content}</span>
                    : <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>}
                  {message.execution?.length ? (
                    <details className="mt-1.5 border-t border-border/50 pt-1.5 text-xs">
                      <summary className="cursor-pointer text-muted-foreground">Execution · {message.execution.length} steps</summary>
                      <ul className="mt-1 grid gap-0.5">
                        {message.execution.map((step, stepIndex) => (
                          <li key={stepIndex} className="flex items-center gap-2">
                            <span className={`frame-dot ${step.state}`} />
                            <code className="text-[11px]">{step.step}</code>
                            <em className="not-italic text-muted-foreground">{step.state}</em>
                            <small className="ml-auto text-muted-foreground">{step.duration}</small>
                          </li>
                        ))}
                      </ul>
                    </details>
                  ) : null}
                </Bubble>
              ))}
              {flowBusy ? (
                <Bubble role="assistant" senderName="AI">
                  <span className="lf-shimmer text-sm font-medium">Flow running…</span>
                </Bubble>
              ) : null}
            </> : (
              <EmptyState
                subtitle="Test your flow with a chat prompt"
                hint={targetInput
                  ? <>Your message is passed as <code>${`{inputs.${targetInput.name}}`}</code></>
                  : 'Add a string Flow Input to feed your message into the flow.'}
              />
            )
          ) : (
            hasModel ? <>
              {modelMessages.map((message, index) => (
                <Bubble key={index} role={message.role} senderName={message.role === 'user' ? 'User' : 'AI'} copyText={message.content}
                  onEdit={message.role === 'user' && !chatRequestId ? () => { setModelInput(message.content); setModelMessages((current) => current.slice(0, index)); inputRef.current?.focus(); } : undefined}
                  onFeedback={message.role === 'assistant' && sessionId ? (value) => { void request('chat.feedback', { session_id: sessionId, message_id: `model-${index}`, value }); } : undefined}>
                  {message.role === 'user'
                    ? <span className="whitespace-pre-wrap">{message.content}</span>
                    : <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>}
                </Bubble>
              ))}
              {streaming || chatRequestId ? (
                <Bubble role="assistant" senderName="AI">
                  {streaming ? <ReactMarkdown remarkPlugins={[remarkGfm]}>{streaming}</ReactMarkdown> : <span className="animate-pulse text-muted-foreground">…</span>}
                </Bubble>
              ) : null}
            </> : (
              <EmptyState subtitle="Chat directly with a model" hint="No agent, no flow — straight to model_manager." />
            )
          )}
          <div ref={endRef} />
        </div>
      </div>

      {/* No Chat Input → a "Run Flow" block instead of the composer (Langflow no-input.tsx) */}
      {tab === 'flow' && !targetInput ? (
        <div className="mx-auto w-full max-w-[768px] px-4 pb-4 md:w-5/6">
          <div className="flex w-full flex-col items-center justify-center gap-3 rounded-md border border-input bg-muted p-2 py-4">
            {!flowBusy ? (
              <Button className="font-semibold" onClick={() => void runFlowNoInput()} disabled={!connected}>Run Flow</Button>
            ) : (
              <Button unstyled disabled className="cursor-default rounded-md bg-muted px-2.5 py-1.5 text-foreground">
                <div className="flex items-center gap-2 text-sm font-medium">Running<Loader2 className="h-4 w-4 animate-spin" /></div>
              </Button>
            )}
            <p className="text-sm text-muted-foreground">This flow has no Chat Input — run it directly, or add a Chat Input node to send messages.</p>
          </div>
        </div>
      ) : (
      /* Composer — bordered focus-reactive card (Langflow input-wrapper.tsx) */
      <div className="mx-auto w-full max-w-[768px] px-4 pb-4 md:w-5/6">
        <div
          data-testid="input-wrapper"
          className={cn(
            'flex w-full cursor-text flex-col rounded-2xl border bg-background p-3.5 shadow-[0_18px_44px_rgba(0,0,0,0.16)] transition-colors hover:border-muted-foreground focus-within:border-primary focus-within:shadow-[0_18px_44px_rgba(0,0,0,0.22)]',
            dragging ? 'border-primary' : 'border-input',
          )}
          onClick={(event) => {
            const target = event.target as HTMLElement;
            if (target.closest("textarea,button,input,[role='button']")) return;
            inputRef.current?.focus();
          }}
          onDragOver={tab === 'flow' ? (event) => { event.preventDefault(); setDragging(true); } : undefined}
          onDragLeave={tab === 'flow' ? () => setDragging(false) : undefined}
          onDrop={tab === 'flow' ? (event) => { event.preventDefault(); setDragging(false); if (event.dataTransfer.files.length) void uploadFiles(event.dataTransfer.files); } : undefined}
        >
          {tab === 'flow' && attached.length ? (
            <div className="flex w-full flex-wrap items-center gap-2 pb-3">
              {attached.map((file) => (
                <div key={file.id} className="flex items-center gap-1.5 rounded-md border border-border bg-background px-2 py-1 text-xs">
                  <FileText className="h-3.5 w-3.5 text-muted-foreground" />
                  <span className="max-w-[160px] truncate">{file.name}</span>
                  <button type="button" onClick={() => removeAttached(file.id)} className="text-muted-foreground hover:text-destructive" aria-label="Remove file"><X className="h-3 w-3" /></button>
                </div>
              ))}
            </div>
          ) : null}
          <div className="w-full">
            <Textarea
              ref={inputRef}
              rows={1}
              data-testid="input-chat-playground"
              className="custom-scroll !min-h-0 block w-full resize-none !border-0 !bg-transparent p-0 text-sm leading-relaxed text-foreground !shadow-none placeholder:text-muted-foreground !outline-none focus:!outline-none focus-visible:!outline-none focus-visible:!ring-0 focus-visible:!ring-offset-0"
              style={{ maxHeight: `${CHAT_INPUT_MAX_HEIGHT}px` }}
              placeholder={placeholder}
              value={value}
              disabled={inputDisabled}
              onChange={(event) => {
                if (tab === 'flow') setFlowInput(event.target.value); else setModelInput(event.target.value);
                resizeTextarea(event.target, event.target.value);
              }}
              onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); onSend(); } }}
            />
          </div>
          <div className="flex w-full items-center justify-between pt-3">
            <div className="flex-shrink-0">
              {tab === 'flow' ? (
                <>
                  <input ref={fileInputRef} type="file" multiple className="hidden"
                    onChange={(event) => { if (event.target.files?.length) void uploadFiles(event.target.files); event.target.value = ''; }} />
                  <Button unstyled className="flex h-6 w-6 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary-hover hover:text-foreground disabled:opacity-50"
                    onClick={() => fileInputRef.current?.click()} disabled={!connected || uploading} title="Attach files" aria-label="Attach files">
                    {uploading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Paperclip className="h-4 w-4" />}
                  </Button>
                </>
              ) : null}
            </div>
            <div className="flex flex-1 items-center justify-end gap-3">
              <span className="hidden text-[11px] text-muted-foreground sm:inline">Enter to send · Shift+Enter for a new line</span>
              <Button
                unstyled
                className={cn(
                  'flex h-8 w-8 items-center justify-center rounded-full px-0 transition-colors',
                  'bg-primary text-primary-foreground hover:bg-primary-hover hover:text-secondary',
                  !busy && !canSend && 'pointer-events-none opacity-40',
                )}
                onClick={busy ? onStop : onSend}
                disabled={inputDisabled}
                data-testid={busy ? 'button-stop' : 'button-send'}
                aria-label={busy ? 'Stop' : 'Send'}
                title={busy ? 'Stop' : 'Send'}
              >
                {busy ? <Square className="h-3.5 w-3.5" fill="currentColor" aria-hidden /> : <ArrowUp className="h-[18px] w-[18px]" />}
              </Button>
            </div>
          </div>
        </div>
      </div>
      )}
        </div>
      </div>
    </aside>
  );
}
