import { useCallback, useEffect, useRef, useState } from 'react';

import api, { getAccessToken, resolveMediaUrl } from '../api';

const WS_ROOT = process.env.REACT_APP_WS_URL ?? 'ws://127.0.0.1:8000';

export type ChatMessageRow = {
  id: string;
  sender_id: number;
  sender_username: string;
  text: string;
  image_url?: string | null;
  created_at: string;
};

function mapMessage(m: {
  id: string;
  sender: { id: number; username: string };
  text: string;
  image_url?: string | null;
  created_at: string;
}): ChatMessageRow {
  return {
    id: m.id,
    sender_id: m.sender.id,
    sender_username: m.sender.username,
    text: m.text,
    image_url: resolveMediaUrl(m.image_url),
    created_at: m.created_at,
  };
}

export function useStaffTaskChat(
  taskId: string | null,
  enabled: boolean,
): {
  messages: ChatMessageRow[];
  sendMessage: (text: string, image?: File) => Promise<void>;
  reloadMessages: () => Promise<void>;
  connected: boolean;
  sending: boolean;
  error: string | null;
} {
  const [messages, setMessages] = useState<ChatMessageRow[]>([]);
  const [connected, setConnected] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const socketRef = useRef<WebSocket | null>(null);

  const reloadMessages = useCallback(async (): Promise<void> => {
    if (!taskId) {
      setMessages([]);
      return;
    }
    const r = await api.get(`/staff-tasks/${taskId}/messages/`);
    const rows = Array.isArray(r.data) ? r.data : [];
    setMessages(rows.map(mapMessage));
  }, [taskId]);

  const sendMessage = useCallback(
    async (text: string, image?: File): Promise<void> => {
      if (!taskId) {
        return;
      }
      const trimmed = text.trim();
      if (!trimmed && !image) {
        return;
      }
      setSending(true);
      setError(null);
      try {
        if (image) {
          const form = new FormData();
          form.append('text', trimmed);
          form.append('image', image);
          await api.post(`/staff-tasks/${taskId}/messages/`, form, {
            headers: { 'Content-Type': 'multipart/form-data' },
          });
        } else {
          await api.post(`/staff-tasks/${taskId}/messages/`, { text: trimmed });
        }
        await reloadMessages();
      } catch (err: unknown) {
        const detail =
          err &&
          typeof err === 'object' &&
          'response' in err &&
          (err as { response?: { data?: { detail?: string } } }).response?.data?.detail;
        setError(typeof detail === 'string' ? detail : 'Не удалось отправить сообщение.');
      } finally {
        setSending(false);
      }
    },
    [taskId, reloadMessages],
  );

  useEffect(() => {
    if (!enabled || !taskId) {
      setConnected(false);
      setMessages([]);
      setError(null);
      return undefined;
    }

    void reloadMessages().catch(() => {
      setError('Не удалось загрузить сообщения чата.');
    });

    const token = getAccessToken();
    if (!token) {
      return undefined;
    }

    const socket = new WebSocket(
      `${WS_ROOT}/ws/staff-tasks/${taskId}/chat/?token=${encodeURIComponent(token)}`,
    );
    socketRef.current = socket;
    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data as string) as {
          event: string;
          data?: ChatMessageRow;
        };
        if (payload.event === 'chat.message' && payload.data) {
          const row: ChatMessageRow = {
            ...payload.data,
            image_url: resolveMediaUrl(payload.data.image_url),
          };
          setMessages((prev) => {
            if (prev.some((m) => m.id === row.id)) {
              return prev;
            }
            return [...prev, row];
          });
        }
      } catch {
        // ignore malformed frames
      }
    };
    return () => {
      socket.close();
      socketRef.current = null;
    };
  }, [enabled, taskId, reloadMessages]);

  return { messages, sendMessage, reloadMessages, connected, sending, error };
}
