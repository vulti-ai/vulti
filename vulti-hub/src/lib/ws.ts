import { writable, type Readable } from 'svelte/store';
import { getToken } from './api';

export type WsStatus = 'connecting' | 'connected' | 'disconnected';

export interface WsMessage {
	type: 'chunk' | 'message' | 'typing' | 'notification' | 'error';
	content?: string;
	id?: string;
	active?: boolean;
	source?: string;
	summary?: string;
	actions?: string[];
	notification_id?: string;
}

interface WsStore {
	status: Readable<WsStatus>;
	connect(sessionId: string): void;
	disconnect(): void;
	send(content: string, attachments?: File[]): void;
	sendAction(notificationId: string, action: string): void;
	onMessage: (handler: (msg: WsMessage) => void) => () => void;
}

export function createWsStore(): WsStore {
	let ws: WebSocket | null = null;
	let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
	let currentSessionId: string | null = null;
	const handlers = new Set<(msg: WsMessage) => void>();
	const status = writable<WsStatus>('disconnected');

	function connect(sessionId: string) {
		currentSessionId = sessionId;
		if (ws) {
			ws.close();
		}

		const token = getToken();
		const wsUrl = `ws://localhost:8080/ws/${sessionId}${token ? `?token=${token}` : ''}`;
		status.set('connecting');

		ws = new WebSocket(wsUrl);

		ws.onopen = () => {
			status.set('connected');
			if (reconnectTimer) {
				clearTimeout(reconnectTimer);
				reconnectTimer = null;
			}
		};

		ws.onmessage = (event) => {
			try {
				const msg: WsMessage = JSON.parse(event.data);
				handlers.forEach((h) => h(msg));
			} catch {
				// ignore parse errors
			}
		};

		ws.onclose = () => {
			status.set('disconnected');
			// Auto-reconnect after 2s
			if (currentSessionId) {
				reconnectTimer = setTimeout(() => {
					if (currentSessionId) connect(currentSessionId);
				}, 2000);
			}
		};

		ws.onerror = () => {
			ws?.close();
		};
	}

	function disconnect() {
		currentSessionId = null;
		if (reconnectTimer) {
			clearTimeout(reconnectTimer);
			reconnectTimer = null;
		}
		if (ws) {
			ws.close();
			ws = null;
		}
		status.set('disconnected');
	}

	function send(content: string) {
		if (ws?.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({ type: 'message', content }));
		}
	}

	function sendAction(notificationId: string, action: string) {
		if (ws?.readyState === WebSocket.OPEN) {
			ws.send(JSON.stringify({ type: 'action', notification_id: notificationId, action }));
		}
	}

	function onMessage(handler: (msg: WsMessage) => void) {
		handlers.add(handler);
		return () => handlers.delete(handler);
	}

	return { status, connect, disconnect, send, sendAction, onMessage };
}
