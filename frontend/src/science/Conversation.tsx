import { useEffect, useRef, useState } from 'react';
import { ArrowUp, Loader2 } from 'lucide-react';

import { MessageMarkdown } from '../components/common/Markdown';
import type { RequestFn } from '../canvas/types';
import type { GatewayEvent } from '../controllers/gateway';

interface Entry { id: string; role: 'user' | 'agent' | 'system'; title: string; content: string; timestamp: string }
interface Step { id: string; label: string; detail?: string }

/** The Science conversation: you talk, the agent runs the experiment.
 *
 * Its own conversation, not the Chat one — the conversation layer keys a
 * transcript by (project, view), so asking here does not appear in Chat and
 * vice versa. See autogenesis/conversation/README.md.
 *
 * The agent runs its code in the BASE environment's kernel, not the
 * workstation's — tools ship with the agent system and run beside it. The
 * Notebook tab talks to the science container's kernel instead. They share the
 * project's workspace, so files written by one are readable by the other, but
 * NOT the in-memory state: a variable the agent defined is not defined in a
 * notebook cell. */
export function ScienceConversation({ request, subscribe, sessionId, connected }: {
  request: RequestFn;
  subscribe: (listener: (event: GatewayEvent) => void) => () => void;
  sessionId: string;
  connected: boolean;
}) {
  const [entries, setEntries] = useState<Entry[]>([]);
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  // What the agent is doing right now. Without this the pane showed a bare
  // spinner from submit to completion — the same wait Chat fills with its
  // activity stream, which made an identical run feel far slower here.
  const [steps, setSteps] = useState<Step[]>([]);
  const [conversationId, setConversationId] = useState<string>();
  const bottom = useRef<HTMLDivElement>(null);

  // Resume this project's science conversation, so a refresh does not open on
  // an empty pane while the transcript sits on disk.
  useEffect(() => {
    let cancelled = false;
    void (async () => {
      const listed = await request('conversation.list', { session_id: sessionId, view: 'science' });
      if (cancelled || !listed.ok) return;
      const conversations = (listed.result as { conversations?: Array<{ conversation_id: string }> }).conversations ?? [];
      const latest = conversations[0]?.conversation_id;
      if (!latest) return;
      setConversationId(latest);
      const replay = await request('conversation.events', { session_id: sessionId, conversation_id: latest });
      if (cancelled || !replay.ok) return;
      const events = (replay.result as { events?: GatewayEvent[] }).events ?? [];
      setEntries(events.flatMap(toEntry));
    })();
    return () => { cancelled = true; };
  }, [request, sessionId]);

  const conversationRef = useRef<string | undefined>(undefined);
  conversationRef.current = conversationId;
  useEffect(() => subscribe((event) => {
    // Everything on this socket arrives here: other projects, other views, the
    // canvas. Only this conversation's belongs in this transcript.
    if (event.session_id !== sessionId) return;
    if (conversationRef.current && event.conversation_id && event.conversation_id !== conversationRef.current) return;
    if (event.type === 'task.started' || event.type === 'trace.event') {
      const step = toStep(event);
      // Bounded: a long run emits hundreds, and only the recent ones say
      // anything about what is happening now.
      if (step) setSteps((current) => [...current, step].slice(-40));
      return;
    }
    const produced = toEntry(event);
    if (produced.length) setEntries((current) => [...current, ...produced]);
    if (event.type === 'task.submitted') setSteps([]);
    if (event.type === 'task.completed' || event.type === 'task.failed') {
      setBusy(false);
      setSteps([]);
    }
  }), [subscribe, sessionId]);

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth' }); }, [entries.length]);

  const submit = async () => {
    const content = draft.trim();
    if (!content || busy || !connected) return;
    setDraft('');
    setBusy(true);
    const response = await request('task.submit', {
      session_id: sessionId, content, view: 'science',
      ...(conversationId ? { conversation_id: conversationId } : {}),
    });
    if (response.ok) {
      const id = (response.result as { conversation_id?: string }).conversation_id;
      if (id) setConversationId(id);
    } else {
      setBusy(false);
      setEntries((current) => [...current, {
        id: `error-${current.length}`, role: 'system', title: 'Could not submit',
        content: response.error?.message ?? 'Unknown error', timestamp: new Date().toISOString(),
      }]);
    }
  };

  return (
    <section className="science-conversation">
      <div className="science-thread">
        {entries.length ? entries.map((entry) => (
          <article className={`science-message ${entry.role}`} key={entry.id}>
            <div className="science-message-avatar">{entry.role === 'user' ? 'You' : '✦'}</div>
            <div className="science-message-body">
              <div className="science-message-heading"><strong>{entry.title}</strong></div>
              {entry.role === 'user'
                ? <p>{entry.content}</p>
                : <MessageMarkdown content={entry.content} />}
            </div>
          </article>
        )) : (
          <div className="science-thread-empty">
            <strong>What should we try?</strong>
            <p>Describe an experiment and the agent runs it, leaving its results in this
               project's workspace. The Notebook tab is a kernel on those same files —
               yours to poke at, and the agent's too whenever it runs a cell.</p>
          </div>
        )}
        {busy ? (
          <div className="science-progress">
            <div className="science-working"><Loader2 className="science-spinner" /> Working…</div>
            {steps.length ? (
              <ol className="science-steps">
                {steps.map((step) => (
                  <li key={step.id}><strong>{step.label}</strong>{step.detail ? <span>{step.detail}</span> : null}</li>
                ))}
              </ol>
            ) : null}
          </div>
        ) : null}
        <div ref={bottom} />
      </div>
      <div className="science-composer">
        <textarea
          value={draft}
          placeholder="Ask anything — describe an experiment, or a plot you want"
          rows={1}
          onChange={(event) => setDraft(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) { event.preventDefault(); void submit(); }
          }}
        />
        <button onClick={() => void submit()} disabled={!draft.trim() || busy || !connected} aria-label="Send">
          <ArrowUp size={15} strokeWidth={2.2} />
        </button>
      </div>
    </section>
  );
}

/** Gateway events that belong in a transcript, as transcript entries.
 *
 * Only the ones a reader wants: the ask, and the answer. Tool-by-tool progress
 * is what the Chat view's activity rail is for, and repeating it here would
 * bury the result the experiment was run for. */
/** A trace event as one readable line: what acted, and on what.
 *
 * Deliberately thinner than the Chat view's activity cards — this pane is for
 * reading the result, and a full trace tree would bury it. */
function toStep(event: GatewayEvent): Step | null {
  if (event.type === 'task.started') return { id: `${event.seq_no}`, label: 'Meta agent started' };
  const trace = (event.payload ?? {}) as Record<string, unknown>;
  const kind = String(trace.event_type ?? '');
  // The *_start halves would double every line; the finished ones carry the
  // outcome, which is what a reader wants.
  if (kind.endsWith('_start')) return null;
  const actor = String(trace.action_name ?? trace.agent_name ?? trace.label ?? 'agent');
  const input = (trace.input ?? {}) as Record<string, unknown>;
  const detail = String(input.command ?? input.path ?? input.file_path ?? input.code ?? '')
    .split('\n')[0].slice(0, 90);
  return { id: `${event.seq_no}`, label: actor, detail: detail || undefined };
}

function toEntry(event: GatewayEvent): Entry[] {
  const payload = (event.payload ?? {}) as Record<string, unknown>;
  const stamp = event.timestamp ?? new Date().toISOString();
  if (event.type === 'task.submitted') {
    return [{ id: `${event.seq_no}:user`, role: 'user', title: 'You', content: String(payload.content ?? ''), timestamp: stamp }];
  }
  if (event.type === 'task.completed') {
    const text = String(payload.message ?? payload.result ?? 'Task completed').trim();
    return text ? [{ id: `${event.seq_no}:agent`, role: 'agent', title: 'Agent', content: text, timestamp: stamp }] : [];
  }
  if (event.type === 'task.failed') {
    return [{ id: `${event.seq_no}:failed`, role: 'system', title: 'Failed', content: String(payload.error ?? payload.message ?? 'The task failed.'), timestamp: stamp }];
  }
  return [];
}
