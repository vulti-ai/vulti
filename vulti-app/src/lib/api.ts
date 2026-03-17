const API_BASE = 'http://localhost:8080/api';

let authToken: string | null = null;

export function setToken(token: string) {
	authToken = token;
	localStorage.setItem('vulti_token', token);
}

export function getToken(): string | null {
	if (!authToken) {
		authToken = localStorage.getItem('vulti_token');
	}
	return authToken;
}

export function clearToken() {
	authToken = null;
	localStorage.removeItem('vulti_token');
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const token = getToken();
	const res = await fetch(`${API_BASE}${path}`, {
		...options,
		headers: {
			'Content-Type': 'application/json',
			...(token ? { Authorization: `Bearer ${token}` } : {}),
			...options.headers
		}
	});
	if (!res.ok) {
		const body = await res.text();
		throw new Error(`API ${res.status}: ${body}`);
	}
	return res.json();
}

export const api = {
	// Auth
	auth(token: string) {
		return request<{ ok: boolean }>('/auth', {
			method: 'POST',
			body: JSON.stringify({ token })
		});
	},

	// Sessions
	listSessions() {
		return request<Session[]>('/sessions');
	},
	createSession(name?: string) {
		return request<Session>('/sessions', {
			method: 'POST',
			body: JSON.stringify({ name })
		});
	},
	deleteSession(id: string) {
		return request<void>(`/sessions/${id}`, { method: 'DELETE' });
	},
	getHistory(sessionId: string) {
		return request<Message[]>(`/sessions/${sessionId}/history`);
	},

	// Agents
	listAgents() {
		return request<Agent[]>('/agents');
	},

	// Cron
	listCron() {
		return request<CronJob[]>('/cron');
	},
	createCron(job: Partial<CronJob>) {
		return request<CronJob>('/cron', {
			method: 'POST',
			body: JSON.stringify(job)
		});
	},
	updateCron(id: string, updates: Partial<CronJob>) {
		return request<CronJob>(`/cron/${id}`, {
			method: 'PUT',
			body: JSON.stringify(updates)
		});
	},
	deleteCron(id: string) {
		return request<void>(`/cron/${id}`, { method: 'DELETE' });
	},

	// Inbox & Contacts
	getInbox() {
		return request<InboxItem[]>('/inbox');
	},
	getContacts() {
		return request<Contact[]>('/contacts');
	},

	// Integrations
	getIntegrations() {
		return request<Integration[]>('/integrations');
	},

	// Memories & Soul
	getMemories() {
		return request<Memories>('/memories');
	},
	updateMemory(file: 'memory' | 'user', content: string) {
		return request<{ ok: boolean }>('/memories', {
			method: 'PUT',
			body: JSON.stringify({ file, content })
		});
	},
	getSoul() {
		return request<{ content: string }>('/soul');
	},
	updateSoul(content: string) {
		return request<{ ok: boolean }>('/soul', {
			method: 'PUT',
			body: JSON.stringify({ content })
		});
	},

	// System Status
	getStatus() {
		return request<SystemStatus>('/status');
	},
	getChannels() {
		return request<ChannelDirectory>('/channels');
	},

	// Secrets & OAuth
	getSecrets() {
		return request<Secret[]>('/secrets');
	},
	getOAuth() {
		return request<OAuthToken[]>('/oauth');
	},

	// Analytics
	getAnalytics(days: number = 30) {
		return request<Analytics>(`/analytics?days=${days}`);
	}
};

// Types
export interface Session {
	id: string;
	name: string;
	created_at: string;
	updated_at: string;
	preview?: string;
}

export interface Message {
	id: string;
	role: 'user' | 'assistant';
	content: string;
	timestamp: string;
}

export interface Agent {
	id: string;
	name: string;
	url: string;
	status: 'connected' | 'disconnected' | 'error';
	platforms: string[];
}

export interface CronJob {
	id: string;
	name: string;
	prompt: string;
	schedule: string;
	status: 'active' | 'paused';
	last_run?: string;
	last_output?: string;
}

export interface InboxItem {
	id: string;
	source: string;
	sender: string;
	preview: string;
	timestamp: string;
	read: boolean;
	actions: string[];
}

export interface Contact {
	id: string;
	name: string;
	platforms: { platform: string; handle: string }[];
	last_interaction?: string;
	tags: string[];
}

export interface Integration {
	id: string;
	name: string;
	category: string;
	status: string;
	details: Record<string, any>;
	updated_at?: string;
}

export interface Memories {
	memory: string;
	user: string;
}

export interface Secret {
	key: string;
	masked_value: string;
	is_set: boolean;
	category: string;
}

export interface OAuthToken {
	service: string;
	valid: boolean;
	scopes?: string[];
	has_refresh?: boolean;
}

export interface SystemStatus {
	pid?: number;
	kind?: string;
	gateway_state: string;
	platforms: Record<string, { state: string; updated_at?: string }>;
}

export interface ChannelDirectory {
	updated_at?: string;
	platforms: Record<string, { id: string; name: string; type: string }[]>;
}

// Gateway types
export type ServiceCategory =
	| 'ai_models' | 'communication' | 'files'
	| 'calendar_contacts' | 'knowledge' | 'code' | 'other';

export interface AgentService {
	id: string;
	category: ServiceCategory;
	type: string;
	label: string;
	status: 'connected' | 'pending' | 'error';
	config: Record<string, unknown>;
}

export interface GatewayAgent {
	id: string;
	name: string;
	avatar?: string;
	personality?: string;
	status: 'setting_up' | 'ready' | 'error';
	services: AgentService[];
	createdAt: string;
}

export interface GlobalSettings {
	tailscale: { ip: string; connected: boolean };
}

export interface GatewayState {
	global: GlobalSettings;
	agents: GatewayAgent[];
	activeAgentId: string | null;
}

export interface Analytics {
	empty?: boolean;
	error?: string;
	days?: number;
	overview?: {
		total_sessions: number;
		total_messages: number;
		total_tool_calls: number;
		total_input_tokens: number;
		total_output_tokens: number;
		total_tokens: number;
		estimated_cost: number;
		total_hours: number;
		avg_session_duration: number;
		avg_messages_per_session: number;
		user_messages: number;
		assistant_messages: number;
	};
	models?: { model: string; sessions: number; total_tokens: number; cost: number }[];
	platforms?: { platform: string; sessions: number; messages: number; total_tokens: number }[];
	tools?: { tool_name: string; call_count: number; sessions: number }[];
	activity?: {
		hourly_distribution: number[];
		daily_distribution: number[];
		sessions_by_day: Record<string, number>;
	};
}
