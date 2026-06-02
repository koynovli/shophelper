import { useCallback, useEffect, useRef, useState } from 'react';

import api, { getAccessToken, resolveMediaUrl } from '../api';

const WS_ROOT = process.env.REACT_APP_WS_URL ?? 'ws://127.0.0.1:8000';

export type PlacementChatMessage = {
  id: string;
  text: string;
  image_url: string | null;
  sender_username?: string;
  created_at: string;
};

type Props = {
  taskId: string;
  enabled?: boolean;
};

export function usePlacementTaskChat({ taskId, enabled = true }: Props) {
  const [messages, setMessages] = useState<PlacementChatMessage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!enabled || !taskId) {
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const { data } = await api.get<PlacementChatMessage[]>(
        `/placement-tasks/${taskId}/messages/`,
      );
      setMessages(
        data.map((m) => ({
          ...m,
          image_url: m.image_url ? resolveMediaUrl(m.image_url) : null,
        })),
      );
    } catch {
      setError('Не удалось загрузить сообщения.');
    } finally {
      setLoading(false);
    }
  }, [enabled, taskId]);

  useEffect(() => {
    void load();
  }, [load]);

  const appendRef = useRef<(msg: PlacementChatMessage) => void>(() => {});
  appendRef.current = (msg) => {
    setMessages((prev) => {
      if (prev.some((m) => m.id === msg.id)) {
        return prev;
      }
      return [...prev, msg];
    });
  };

  useEffect(() => {
    if (!enabled || !taskId) {
      return undefined;
    }
    const token = getAccessToken();
    if (!token) {
      return undefined;
    }
    const socket = new WebSocket(
      `${WS_ROOT}/ws/chat/${taskId}/?token=${encodeURIComponent(token)}`,
    );
    socket.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data as string) as {
          event: string;
          data: PlacementChatMessage & { sender_username?: string };
        };
        if (frame.event === 'chat.message' && frame.data) {
          appendRef.current({
            id: frame.data.id,
            text: frame.data.text,
            image_url: frame.data.image_url
              ? resolveMediaUrl(frame.data.image_url)
              : null,
            sender_username: frame.data.sender_username,
            created_at: frame.data.created_at,
          });
        }
      } catch {
        // ignore
      }
    };
    return () => socket.close();
  }, [enabled, taskId]);

  const send = useCallback(
    async (text: string, image?: File) => {
      const form = new FormData();
      form.append('text', text);
      if (image) {
        form.append('image', image);
      }
      const { data } = await api.post<PlacementChatMessage>(
        `/placement-tasks/${taskId}/messages/`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      );
      appendRef.current({
        ...data,
        image_url: data.image_url ? resolveMediaUrl(data.image_url) : null,
      });
    },
    [taskId],
  );

  return { messages, loading, error, reload: load, send };
}
