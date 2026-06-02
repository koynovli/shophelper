import { useCallback, useEffect, useRef } from 'react';

import { getAccessToken } from '../api';

const WS_ROOT = process.env.REACT_APP_WS_URL ?? 'ws://127.0.0.1:8000';

type TaskPoolEvent = {
  event: string;
  data: Record<string, unknown>;
};

export function useTaskPoolWebSocket(onEvent: (event: TaskPoolEvent) => void): void {
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  const connect = useCallback(() => {
    const token = getAccessToken();
    if (!token) {
      return undefined;
    }
    const socket = new WebSocket(`${WS_ROOT}/ws/task-pool/?token=${encodeURIComponent(token)}`);
    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data as string) as TaskPoolEvent;
        handlerRef.current(payload);
      } catch {
        // ignore malformed frames
      }
    };
    return socket;
  }, []);

  useEffect(() => {
    let socket = connect();
    const interval = window.setInterval(() => {
      if (socket && socket.readyState === WebSocket.CLOSED) {
        socket = connect();
      }
    }, 5000);
    return () => {
      window.clearInterval(interval);
      socket?.close();
    };
  }, [connect]);
}
