// src/useWebSocket.ts — WebSocket hook connecting to /ws

import { useEffect, useRef, useState, useCallback } from 'react';
import type { WSMessage } from './types';

const isHttps = typeof window !== 'undefined' && window.location.protocol === 'https:';
const wsProto = isHttps ? 'wss:' : 'ws:';
const wsPort = typeof window !== 'undefined'
  ? (window.location.port ? `:${window.location.port}` : (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1' ? ':8000' : ''))
  : ':8000';
const WS_URL = `${wsProto}//${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}${wsPort}/ws`;

export type WSStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

interface UseWebSocketResult {
  message: WSMessage | null;
  wsStatus: WSStatus;
  lastReceived: Date | null;
  reconnect: () => void;
}

export function useWebSocket(): UseWebSocketResult {
  const [message, setMessage] = useState<WSMessage | null>(null);
  const [wsStatus, setWsStatus] = useState<WSStatus>('connecting');
  const [lastReceived, setLastReceived] = useState<Date | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const retryRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const retryCount = useRef(0);

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;

    setWsStatus('connecting');
    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[WS] Connected');
      setWsStatus('connected');
      retryCount.current = 0;
    };

    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data) as WSMessage;
        setMessage(data);
        setLastReceived(new Date());
      } catch {}
    };

    ws.onerror = () => {
      setWsStatus('error');
    };

    ws.onclose = () => {
      setWsStatus('disconnected');
      // Exponential backoff: 1s, 2s, 4s, 8s, max 15s
      const delay = Math.min(1000 * Math.pow(2, retryCount.current), 15000);
      retryCount.current++;
      retryRef.current = setTimeout(() => connect(), delay);
    };
  }, []);

  useEffect(() => {
    connect();
    return () => {
      retryRef.current && clearTimeout(retryRef.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { message, wsStatus, lastReceived, reconnect: connect };
}
