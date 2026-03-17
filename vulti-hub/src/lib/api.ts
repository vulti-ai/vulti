const API_BASE = 'http://localhost:8080/api';

let authToken: string | null = null;

// Auto-load token from Tauri on first use
let tokenLoaded = false;
async function ensureTokenLoaded() {
	if (tokenLoaded) return;
	tokenLoaded = true;
	// Try localStorage first
	if (!authToken) {
		authToken = localStorage.getItem('vulti_token');
		// Validate the stored token works
		if (authToken) {
			try {
				const res = await fetch(`${API_BASE}/status`, {
					headers: { Authorization: `Bearer ${authToken}` },
					signal: AbortSignal.timeout(2000)
				});
				if (res.status === 401) {
					// Stale token, clear it
					authToken = null;
					localStorage.removeItem('vulti_token');
				}
			} catch {
				// Gateway not reachable yet, keep the token
			}
		}
	}
	// Try Tauri if still no token
	if (!authToken && typeof window !== 'undefined' && '__TAURI__' in window) {
		try {
			const { invoke } = await import('@tauri-apps/api/core');
			const token = await invoke<string>('get_gateway_token');
			if (token) {
				authToken = token;
				localStorage.setItem('vulti_token', token);
			}
		} catch {}
	}
	// Fallback: bootstrap from gateway (localhost only)
	if (!authToken) {
		try {
			const res = await fetch(`${API_BASE}/bootstrap`, { signal: AbortSignal.timeout(2000) });
			if (res.ok) {
				const data = await res.json();
				if (data.token) {
					authToken = data.token;
					localStorage.setItem('vulti_token', data.token);
				}
			}
		} catch {}
	}
}

export function setToken(token: string) {
	authToken = token;
	tokenLoaded = true;
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
	await ensureTokenLoaded();
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

	// Sessions (backward compat -- default agent)
	listSessions(agentId?: string) {
		if (agentId) return request<Session[]>(`/agents/${agentId}/sessions`);
		return request<Session[]>('/sessions');
	},
	createSession(agentId?: string, name?: string) {
		if (agentId) {
			return request<Session>(`/agents/${agentId}/sessions`, {
				method: 'POST',
				body: JSON.stringify({ name })
			});
		}
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

	// Agent CRUD
	listAgents() {
		return request<Agent[]>('/agents');
	},
	getAgent(agentId: string) {
		return request<Agent>(`/agents/${agentId}`);
	},
	createAgent(data: { name: string; avatar?: string; personality?: string; description?: string; inherit_from?: string }) {
		return request<Agent>('/agents', {
			method: 'POST',
			body: JSON.stringify(data)
		});
	},
	updateAgent(agentId: string, updates: Partial<Agent>) {
		return request<Agent>(`/agents/${agentId}`, {
			method: 'PUT',
			body: JSON.stringify(updates)
		});
	},
	deleteAgent(agentId: string) {
		return request<{ ok: boolean }>(`/agents/${agentId}`, { method: 'DELETE' });
	},

	// Cron (agent-scoped or default)
	listCron(agentId?: string) {
		if (agentId) return request<CronJob[]>(`/agents/${agentId}/cron`);
		return request<CronJob[]>('/cron');
	},
	createCron(job: Partial<CronJob>, agentId?: string) {
		if (agentId) {
			return request<CronJob>(`/agents/${agentId}/cron`, {
				method: 'POST',
				body: JSON.stringify(job)
			});
		}
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

	// Rules
	listRules() {
		return request<Rule[]>('/rules');
	},
	createRule(rule: Partial<Rule>) {
		return request<Rule>('/rules', {
			method: 'POST',
			body: JSON.stringify(rule)
		});
	},
	updateRule(id: string, updates: Partial<Rule>) {
		return request<Rule>(`/rules/${id}`, {
			method: 'PUT',
			body: JSON.stringify(updates)
		});
	},
	deleteRule(id: string) {
		return request<void>(`/rules/${id}`, { method: 'DELETE' });
	},

	// Inbox & Contacts (global)
	getInbox() {
		return request<InboxItem[]>('/inbox');
	},
	getContacts() {
		return request<Contact[]>('/contacts');
	},

	// Integrations (global)
	getIntegrations() {
		return request<Integration[]>('/integrations');
	},

	// Memories & Soul (agent-scoped or default)
	getMemories(agentId?: string) {
		if (agentId) return request<Memories>(`/agents/${agentId}/memories`);
		return request<Memories>('/memories');
	},
	updateMemory(file: 'memory' | 'user', content: string, agentId?: string) {
		if (agentId) {
			return request<{ ok: boolean }>(`/agents/${agentId}/memories`, {
				method: 'PUT',
				body: JSON.stringify({ file, content })
			});
		}
		return request<{ ok: boolean }>('/memories', {
			method: 'PUT',
			body: JSON.stringify({ file, content })
		});
	},
	getSoul(agentId?: string) {
		if (agentId) return request<{ content: string }>(`/agents/${agentId}/soul`);
		return request<{ content: string }>('/soul');
	},
	updateSoul(content: string, agentId?: string) {
		if (agentId) {
			return request<{ ok: boolean }>(`/agents/${agentId}/soul`, {
				method: 'PUT',
				body: JSON.stringify({ content })
			});
		}
		return request<{ ok: boolean }>('/soul', {
			method: 'PUT',
			body: JSON.stringify({ content })
		});
	},

	// System Status (global)
	getStatus() {
		return request<SystemStatus>('/status');
	},
	getChannels() {
		return request<ChannelDirectory>('/channels');
	},

	// Secrets & OAuth (global)
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

// Unified Agent type (merges old Agent + GatewayAgent)
export interface Agent {
	id: string;
	name: string;
	url?: string;
	avatar?: string;
	personality?: string;
	description?: string;
	model?: string;
	status: 'setting_up' | 'ready' | 'active' | 'connected' | 'disconnected' | 'stopped' | 'error';
	services?: AgentService[];
	platforms?: string[];
	createdAt?: string;
	createdFrom?: string | null;
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

export interface Rule {
	id: string;
	name: string;
	condition: string;
	action: string;
	enabled: boolean;
	priority: number;
	trigger_count: number;
	max_triggers?: number | null;
	cooldown_minutes?: number | null;
	last_triggered_at?: string | null;
	tags: string[];
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

// Service types
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

// Keep GatewayAgent as alias for backward compat
export type GatewayAgent = Agent;

export interface GlobalSettings {
	tailscale: { ip: string; connected: boolean };
	gateway: { connected: boolean };
}

export interface GatewayState {
	global: GlobalSettings;
	agents: Agent[];
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
