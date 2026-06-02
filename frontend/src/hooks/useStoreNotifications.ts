import { useCallback, useEffect, useRef } from 'react';

import { getAccessToken } from '../api';

const WS_ROOT = process.env.REACT_APP_WS_URL ?? 'ws://127.0.0.1:8000';

export type StoreNotificationEvent = {
  event: string;
  data: {
    message?: string;
    product_name?: string;
    quantity?: number;
    equipment_name?: string;
    [key: string]: unknown;
  };
};

export function useStoreNotifications(
  onNotify: (event: StoreNotificationEvent) => void,
): void {
  const handlerRef = useRef(onNotify);
  handlerRef.current = onNotify;

  const connect = useCallback(() => {
    const token = getAccessToken();
    if (!token) {
      return undefined;
    }
    const socket = new WebSocket(
      `${WS_ROOT}/ws/notifications/?token=${encodeURIComponent(token)}`,
    );
    socket.onmessage = (message) => {
      try {
        const payload = JSON.parse(message.data as string) as StoreNotificationEvent;
        handlerRef.current(payload);
      } catch {
        // ignore
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
