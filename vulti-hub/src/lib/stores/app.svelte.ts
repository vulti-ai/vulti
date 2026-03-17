import { api, setToken, getToken, type Session, type Message, type Agent, type AgentService, type CronJob, type Rule, type InboxItem, type Contact, type Memories, type Secret, type OAuthToken, type SystemStatus, type ChannelDirectory, type Analytics, type Integration, type GlobalSettings } from '$lib/api';
import { createWsStore, type WsMessage } from '$lib/ws';

// Re-export types for components
export type { GlobalSettings };
// Re-export types used by setup tabs
export type { Agent as GatewayAgent, ServiceCategory } from '$lib/api';

// Settings persistence (only global settings, not agents)
const DEFAULT_SETTINGS: GlobalSettings = {
	tailscale: { ip: '', connected: false },
	gateway: { connected: false }
};

function loadSettingsFromStorage(): GlobalSettings {
	try {
		const saved = localStorage.getItem('vulti_settings');
		if (saved) {
			const parsed = JSON.parse(saved);
			if (!parsed.gateway) parsed.gateway = { connected: false };
			return parsed;
		}
		// Migrate from old key
		const old = localStorage.getItem('vulti_gateway');
		if (old) {
			const parsed = JSON.parse(old);
			if (parsed.global) {
				if (!parsed.global.gateway) parsed.global.gateway = { connected: false };
				return parsed.global;
			}
		}
	} catch {}
	return { ...DEFAULT_SETTINGS };
}

function saveSettingsToStorage() {
	localStorage.setItem('vulti_settings', JSON.stringify(globalSettings));
}

// Global settings state
let globalSettings = $state<GlobalSettings>(loadSettingsFromStorage());

// Reactive state using Svelte 5 runes
let sessions = $state<Session[]>([]);
let activeSessionId = $state<string | null>(null);
let messages = $state<Message[]>([]);
let streamingContent = $state<string>('');
let isStreaming = $state(false);
let isTyping = $state(false);
let agents = $state<Agent[]>([]);
let activeAgentId = $state<string | null>(null);
let cronJobs = $state<CronJob[]>([]);
let rules = $state<Rule[]>([]);
let inbox = $state<InboxItem[]>([]);
let contacts = $state<Contact[]>([]);
let notifications = $state<WsMessage[]>([]);
let sidebarOpen = $state(true);
let currentView = $state<'profile' | 'actions' | 'analytics' | 'config'>('profile');
let authenticated = $state(false);
let memories = $state<Memories>({ memory: '', user: '' });
let soul = $state<string>('');
let secrets = $state<Secret[]>([]);
let oauthTokens = $state<OAuthToken[]>([]);
let systemStatus = $state<SystemStatus>({ gateway_state: 'unknown', platforms: {} });
let channels = $state<ChannelDirectory>({ platforms: {} });
let analytics = $state<Analytics | null>(null);
let integrations = $state<Integration[]>([]);

const ws = createWsStore();

// Subscribe to WebSocket messages
ws.onMessage((msg: WsMessage) => {
	switch (msg.type) {
		case 'chunk':
			streamingContent += msg.content ?? '';
			isStreaming = true;
			break;
		case 'message':
			if (isStreaming) {
				messages = [...messages, {
					id: msg.id ?? crypto.randomUUID(),
					role: 'assistant',
					content: streamingContent || msg.content || '',
					timestamp: new Date().toISOString()
				}];
				streamingContent = '';
				isStreaming = false;
			} else {
				messages = [...messages, {
					id: msg.id ?? crypto.randomUUID(),
					role: 'assistant',
					content: msg.content || '',
					timestamp: new Date().toISOString()
				}];
			}
			isTyping = false;
			break;
		case 'typing':
			isTyping = msg.active ?? false;
			break;
		case 'notification':
			notifications = [msg, ...notifications].slice(0, 50);
			break;
	}
});

export const store = {
	// Global settings (persisted to localStorage)
	get gatewayGlobal() { return globalSettings; },

	updateGlobalSettings(settings: Partial<GlobalSettings>) {
		globalSettings = { ...globalSettings, ...settings };
		saveSettingsToStorage();
	},

	// Agents (from gateway API — source of truth)
	get agents() { return agents; },
	get activeAgentId() { return activeAgentId; },
	set activeAgentId(id: string | null) {
		activeAgentId = id;
		if (id) localStorage.setItem('vulti_active_agent', id);
		else localStorage.removeItem('vulti_active_agent');
	},

	get activeAgent(): Agent | undefined {
		return agents.find(a => a.id === activeAgentId);
	},

	// App state
	get sessions() { return sessions; },
	get activeSessionId() { return activeSessionId; },
	get messages() { return messages; },
	get streamingContent() { return streamingContent; },
	get isStreaming() { return isStreaming; },
	get isTyping() { return isTyping; },
	get cronJobs() { return cronJobs; },
	get rules() { return rules; },
	get inbox() { return inbox; },
	get contacts() { return contacts; },
	get notifications() { return notifications; },
	get sidebarOpen() { return sidebarOpen; },
	set sidebarOpen(v: boolean) { sidebarOpen = v; },
	get currentView() { return currentView; },
	set currentView(v: typeof currentView) { currentView = v; },
	get authenticated() { return authenticated; },
	set authenticated(v: boolean) { authenticated = v; },
	get memories() { return memories; },
	get soul() { return soul; },
	get secrets() { return secrets; },
	get oauthTokens() { return oauthTokens; },
	get systemStatus() { return systemStatus; },
	get channels() { return channels; },
	get analytics() { return analytics; },
	get integrations() { return integrations; },
	ws,

	async loadSessions() {
		try {
			sessions = await api.listSessions(activeAgentId ?? undefined);
		} catch { sessions = []; }
	},

	async createSession(name?: string) {
		const session = await api.createSession(activeAgentId ?? undefined, name);
		sessions = [session, ...sessions];
		await this.switchSession(session.id);
	},

	async switchSession(id: string) {
		activeSessionId = id;
		streamingContent = '';
		isStreaming = false;
		try {
			messages = await api.getHistory(id);
		} catch { messages = []; }
		ws.connect(id);
	},

	async deleteSession(id: string) {
		await api.deleteSession(id);
		sessions = sessions.filter((s) => s.id !== id);
		if (activeSessionId === id) {
			activeSessionId = null;
			messages = [];
			ws.disconnect();
		}
	},

	sendMessage(content: string) {
		messages = [...messages, {
			id: crypto.randomUUID(),
			role: 'user',
			content,
			timestamp: new Date().toISOString()
		}];
		ws.send(content);
		isTyping = true;
	},

	async ensureToken() {
		if (getToken()) return;
		const isTauri = typeof window !== 'undefined' && '__TAURI__' in window;
		if (isTauri) {
			try {
				const { invoke } = await import('@tauri-apps/api/core');
				const token = await invoke<string>('get_gateway_token');
				if (token) setToken(token);
			} catch {}
		}
	},

	async loadAgents() {
		try {
			await this.ensureToken();
			agents = await api.listAgents();
			if (!activeAgentId) {
				const saved = localStorage.getItem('vulti_active_agent');
				if (saved && agents.find(a => a.id === saved)) {
					activeAgentId = saved;
				} else if (agents.length > 0) {
					activeAgentId = agents[0].id;
				}
			}
		} catch { agents = []; }
	},

	async createAgent(data: { name: string; avatar?: string; personality?: string; description?: string; inherit_from?: string }) {
		const agent = await api.createAgent(data);
		agents = [...agents, agent];
		this.activeAgentId = agent.id;
		await this.reloadAgentResources();
		return agent;
	},

	async updateAgent(agentId: string, updates: Partial<Agent>) {
		const updated = await api.updateAgent(agentId, updates);
		agents = agents.map(a => a.id === agentId ? { ...a, ...updated } : a);
		return updated;
	},

	async deleteAgent(agentId: string) {
		await api.deleteAgent(agentId);
		agents = agents.filter(a => a.id !== agentId);
		if (activeAgentId === agentId) {
			this.activeAgentId = agents.length > 0 ? agents[0].id : null;
			if (activeAgentId) await this.reloadAgentResources();
		}
	},

	async addServiceToAgent(agentId: string, service: Partial<AgentService>) {
		// Service management is stored in agent config -- update via API
		const updated = await api.updateAgent(agentId, { services: [...(store.activeAgent?.services ?? []), service as AgentService] } as Partial<Agent>);
		agents = agents.map(a => a.id === agentId ? { ...a, ...updated } : a);
	},

	async removeServiceFromAgent(agentId: string, serviceId: string) {
		const currentServices = store.activeAgent?.services?.filter(s => s.id !== serviceId) ?? [];
		const updated = await api.updateAgent(agentId, { services: currentServices } as Partial<Agent>);
		agents = agents.map(a => a.id === agentId ? { ...a, ...updated } : a);
	},

	async reloadAgentResources() {
		// Clear stale data
		sessions = [];
		messages = [];
		memories = { memory: '', user: '' };
		soul = '';
		cronJobs = [];
		rules = [];
		analytics = null;
		activeSessionId = null;
		ws.disconnect();

		if (!activeAgentId) return;

		await Promise.all([
			this.loadSessions(),
			this.loadMemories(),
			this.loadSoul(),
			this.loadCron(),
		]);
	},

	async loadCron() {
		try { cronJobs = await api.listCron(activeAgentId ?? undefined); } catch { cronJobs = []; }
	},

	async loadRules() {
		try { rules = await api.listRules(); } catch { rules = []; }
	},

	async loadInbox() {
		try { inbox = await api.getInbox(); } catch { inbox = []; }
	},

	async loadContacts() {
		try { contacts = await api.getContacts(); } catch { contacts = []; }
	},

	async loadMemories() {
		try { memories = await api.getMemories(activeAgentId ?? undefined); } catch { memories = { memory: '', user: '' }; }
	},

	async saveMemory(file: 'memory' | 'user', content: string) {
		await api.updateMemory(file, content, activeAgentId ?? undefined);
		if (file === 'memory') memories = { ...memories, memory: content };
		else memories = { ...memories, user: content };
	},

	async loadSoul() {
		try {
			const res = await api.getSoul(activeAgentId ?? undefined);
			soul = res.content;
		} catch { soul = ''; }
	},

	async saveSoul(content: string) {
		await api.updateSoul(content, activeAgentId ?? undefined);
		soul = content;
	},

	async loadSecrets() {
		try { secrets = await api.getSecrets(); } catch { secrets = []; }
	},

	async loadOAuth() {
		try { oauthTokens = await api.getOAuth(); } catch { oauthTokens = []; }
	},

	async loadStatus() {
		try { systemStatus = await api.getStatus(); } catch { systemStatus = { gateway_state: 'unknown', platforms: {} }; }
	},

	async loadChannels() {
		try { channels = await api.getChannels(); } catch { channels = { platforms: {} }; }
	},

	async loadAnalytics(days: number = 30) {
		try { analytics = await api.getAnalytics(days); } catch { analytics = null; }
	},

	async loadIntegrations() {
		try { integrations = await api.getIntegrations(); } catch { integrations = []; }
	},

	dismissNotification(index: number) {
		notifications = notifications.filter((_, i) => i !== index);
	}
};
