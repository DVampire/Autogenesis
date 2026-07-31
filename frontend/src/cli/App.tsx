import React, { useCallback, useEffect, useReducer, useRef, useState } from 'react';
import { Box, Text, useApp, useInput } from 'ink';

import { ApprovalDialog } from './components/ApprovalDialog.js';
import { Composer } from './components/Composer.js';
import { Header } from './components/Header.js';
import { StatusBar } from './components/StatusBar.js';
import { Transcript } from './components/Transcript.js';
import { createGatewayClient, type GatewayClientOptions } from './gateway/index.js';
import { appReducer, initialState } from './state.js';

export function App({ options }: { options: GatewayClientOptions }) {
  const { exit } = useApp();
  const [state, dispatch] = useReducer(appReducer, initialState);
  const [input, setInput] = useState('');
  const clientRef = useRef<ReturnType<typeof createGatewayClient> | undefined>(undefined);
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    const client = createGatewayClient(options);
    clientRef.current = client;
    const unsubscribe = client.onEvent((event) => dispatch({ type: 'event', event }));
    void (async () => {
      try {
        await client.start();
        const hello = await client.request('hello');
        if (!hello.ok) throw new Error(hello.error?.message ?? 'Gateway handshake failed');
        const session = await client.request('session.create', { workspace: options.workspace ?? process.cwd(), name: 'terminal' });
        if (!session.ok || typeof session.result.session_id !== 'string') throw new Error(session.error?.message ?? 'Could not create session');
        dispatch({ type: 'session', sessionId: session.result.session_id });
        dispatch({ type: 'connection', value: 'connected' });
      } catch (error) {
        dispatch({ type: 'connection', value: 'error' });
        dispatch({ type: 'notice', value: error instanceof Error ? error.message : String(error) });
      }
    })();
    return () => {
      unsubscribe();
      void client.close();
    };
  }, [options.configPath, options.connectUrl, options.token, options.workspace]);

  const submit = useCallback(async () => {
    const content = input.trim();
    const sessionId = stateRef.current.sessionId;
    if (!content || !sessionId || stateRef.current.activeTaskId) return;
    setInput('');
    try {
      const response = await clientRef.current?.request('task.submit', { session_id: sessionId, content });
      if (!response?.ok || typeof response.result.task_id !== 'string') throw new Error(response?.error?.message ?? 'Task submission failed');
      dispatch({ type: 'task', taskId: response.result.task_id });
    } catch (error) {
      dispatch({ type: 'notice', value: error instanceof Error ? error.message : String(error) });
    }
  }, [input]);

  const respondToApproval = useCallback(async (decision: 'allow_once' | 'reject') => {
    const approval = stateRef.current.approval;
    if (!approval) return;
    await clientRef.current?.request('approval.respond', {
      approval_id: approval.id,
      session_id: approval.sessionId,
      decision,
    });
    dispatch({ type: 'approval.clear' });
  }, []);

  useInput((character, key) => {
    if (key.ctrl && character === 'c') {
      const taskId = stateRef.current.activeTaskId;
      if (taskId) {
        void clientRef.current?.request('task.cancel', { task_id: taskId });
      } else {
        exit();
      }
      return;
    }
    if (character === 'q' && !input && !stateRef.current.activeTaskId) {
      exit();
      return;
    }
    if (stateRef.current.approval && character === 'a') {
      void respondToApproval('allow_once');
      return;
    }
    if (stateRef.current.approval && character === 'r') {
      void respondToApproval('reject');
      return;
    }
    if (key.return) {
      void submit();
      return;
    }
    if (key.backspace || key.delete) {
      setInput((value) => value.slice(0, -1));
      return;
    }
    if (!key.ctrl && !key.meta && character) setInput((value) => value + character);
  });

  return (
    <Box flexDirection="column">
      <Header connection={state.connection} sessionId={state.sessionId} remote={Boolean(options.connectUrl)} />
      <Transcript entries={state.entries} />
      {state.approval ? <ApprovalDialog approval={state.approval} /> : null}
      <Composer value={input} disabled={!state.sessionId || Boolean(state.activeTaskId)} />
      <StatusBar taskId={state.activeTaskId} notice={state.notice} />
      {state.connection === 'error' ? <Text color="red">Gateway connection failed. Check Python dependencies and configuration.</Text> : null}
    </Box>
  );
}
