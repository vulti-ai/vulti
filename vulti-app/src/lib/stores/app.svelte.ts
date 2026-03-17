import { api, type Session, type Message, type Agent, type CronJob, type InboxItem, type Contact, type Memories, type Secret, type OAuthToken, type SystemStatus, type ChannelDirectory, type Analytics, type Integration, type GatewayAgent, type AgentService, type GlobalSettings, type GatewayState, type ServiceCategory } from '$lib/api';
import { createWsStore, type WsMessage } from '$lib/ws';

// Re-export gateway types for components
export type { GatewayAgent, AgentService, GlobalSettings, GatewayState, ServiceCategory };

// Gateway state persistence
const DEFAULT_GATEWAY: GatewayState = {
	global: { tailscale: { ip: '', connected: false } },
	agents: [],
	activeAgentId: null
};

function loadGatewayFromStorage(): GatewayState {
	try {
		const saved = localStorage.getItem('vulti_gateway');
		if (saved) return JSON.parse(saved);
	} catch {}
	return { ...DEFAULT_GATEWAY };
}

function saveGatewayToStorage() {
	localStorage.setItem('vulti_gateway', JSON.stringify({
		global: gatewayGlobal,
		agents: gatewayAgents,
		activeAgentId: gatewayActiveAgentId
	}));
}

// Gateway state
const savedGateway = loadGatewayFromStorage();
let gatewayGlobal = $state<GlobalSettings>(savedGateway.global);
let gatewayAgents = $state<GatewayAgent[]>(savedGateway.agents);
let gatewayActiveAgentId = $state<string | null>(savedGateway.activeAgentId);

// Reactive state using Svelte 5 runes
let sessions = $state<Session[]>([]);
let activeSessionId = $state<string | null>(null);
let messages = $state<Message[]>([]);
let streamingContent = $state<string>('');
let isStreaming = $state(false);
let isTyping = $state(false);
let agents = $state<Agent[]>([]);
let cronJobs = $state<CronJob[]>([]);
let inbox = $state<InboxItem[]>([]);
let contacts = $state<Contact[]>([]);
let notifications = $state<WsMessage[]>([]);
let sidebarOpen = $state(true);
let currentView = $state<'chat' | 'cron' | 'memories' | 'soul' | 'analytics'>('chat');
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
	// Gateway
	get gateway() { return { global: gatewayGlobal, agents: gatewayAgents, activeAgentId: gatewayActiveAgentId }; },
	get gatewayGlobal() { return gatewayGlobal; },
	get gatewayAgents() { return gatewayAgents; },
	get gatewayActiveAgentId() { return gatewayActiveAgentId; },
	set gatewayActiveAgentId(id: string | null) { gatewayActiveAgentId = id; saveGatewayToStorage(); },

	get activeGatewayAgent(): GatewayAgent | undefined {
		return gatewayAgents.find(a => a.id === gatewayActiveAgentId);
	},

	updateGlobalSettings(settings: Partial<GlobalSettings>) {
		gatewayGlobal = { ...gatewayGlobal, ...settings };
		saveGatewayToStorage();
	},

	createAgent(name: string, avatar?: string): GatewayAgent {
		const agent: GatewayAgent = {
			id: crypto.randomUUID(),
			name,
			avatar,
			status: 'setting_up',
			services: [],
			createdAt: new Date().toISOString()
		};
		gatewayAgents = [...gatewayAgents, agent];
		gatewayActiveAgentId = agent.id;
		saveGatewayToStorage();
		return agent;
	},

	forkAgent(sourceId: string): GatewayAgent | undefined {
		const source = gatewayAgents.find(a => a.id === sourceId);
		if (!source) return undefined;
		const forked: GatewayAgent = {
			...structuredClone(source),
			id: crypto.randomUUID(),
			name: `${source.name} (Copy)`,
			status: 'setting_up',
			createdAt: new Date().toISOString()
		};
		gatewayAgents = [...gatewayAgents, forked];
		gatewayActiveAgentId = forked.id;
		saveGatewayToStorage();
		return forked;
	},

	updateAgent(id: string, updates: Partial<GatewayAgent>) {
		gatewayAgents = gatewayAgents.map(a =>
			a.id === id ? { ...a, ...updates } : a
		);
		saveGatewayToStorage();
	},

	deleteAgent(id: string) {
		gatewayAgents = gatewayAgents.filter(a => a.id !== id);
		if (gatewayActiveAgentId === id) {
			gatewayActiveAgentId = gatewayAgents[0]?.id ?? null;
		}
		saveGatewayToStorage();
	},

	addServiceToAgent(agentId: string, service: AgentService) {
		gatewayAgents = gatewayAgents.map(a =>
			a.id === agentId ? { ...a, services: [...a.services, service] } : a
		);
		saveGatewayToStorage();
	},

	removeServiceFromAgent(agentId: string, serviceId: string) {
		gatewayAgents = gatewayAgents.map(a =>
			a.id === agentId ? { ...a, services: a.services.filter(s => s.id !== serviceId) } : a
		);
		saveGatewayToStorage();
	},

	updateServiceInAgent(agentId: string, serviceId: string, updates: Partial<AgentService>) {
		gatewayAgents = gatewayAgents.map(a =>
			a.id === agentId ? {
				...a,
				services: a.services.map(s => s.id === serviceId ? { ...s, ...updates } : s)
			} : a
		);
		saveGatewayToStorage();
	},

	// App state
	get sessions() { return sessions; },
	get activeSessionId() { return activeSessionId; },
	get messages() { return messages; },
	get streamingContent() { return streamingContent; },
	get isStreaming() { return isStreaming; },
	get isTyping() { return isTyping; },
	get agents() { return agents; },
	get cronJobs() { return cronJobs; },
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
			sessions = await api.listSessions();
		} catch { sessions = []; }
	},

	async createSession(name?: string) {
		const session = await api.createSession(name);
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

	async loadAgents() {
		try { agents = await api.listAgents(); } catch { agents = []; }
	},

	async loadCron() {
		try { cronJobs = await api.listCron(); } catch { cronJobs = []; }
	},

	async loadInbox() {
		try { inbox = await api.getInbox(); } catch { inbox = []; }
	},

	async loadContacts() {
		try { contacts = await api.getContacts(); } catch { contacts = []; }
	},

	async loadMemories() {
		try { memories = await api.getMemories(); } catch { memories = { memory: '', user: '' }; }
	},

	async saveMemory(file: 'memory' | 'user', content: string) {
		await api.updateMemory(file, content);
		if (file === 'memory') memories = { ...memories, memory: content };
		else memories = { ...memories, user: content };
	},

	async loadSoul() {
		try {
			const res = await api.getSoul();
			soul = res.content;
		} catch { soul = ''; }
	},

	async saveSoul(content: string) {
		await api.updateSoul(content);
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
