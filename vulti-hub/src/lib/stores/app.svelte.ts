import { api, setToken, getToken, type Session, type Message, type Agent, type AgentRole, type AgentService, type CronJob, type Rule, type InboxItem, type Contact, type Memories, type Secret, type OAuthToken, type SystemStatus, type ChannelDirectory, type Analytics, type Integration, type GlobalSettings, type Provider, type AgentRelationship, type OwnerProfile, type Connection } from '$lib/api';
import { createWsStore, type WsMessage } from '$lib/ws';
import { marked } from 'marked';

// Configure marked for safe HTML rendering
marked.setOptions({ breaks: true, gfm: true });

// Markdown render cache — avoids re-parsing on session switch
const markdownCache = new Map<string, string>();

function renderMarkdown(text: string): string {
	if (!text) return '';
	const cached = markdownCache.get(text);
	if (cached) return cached;
	try {
		const html = marked.parse(text) as string;
		markdownCache.set(text, html);
		// Evict oldest entries when cache grows large
		if (markdownCache.size > 500) {
			const first = markdownCache.keys().next().value;
			if (first !== undefined) markdownCache.delete(first);
		}
		return html;
	} catch {
		return text;
	}
}

// Re-export types for components
export type { GlobalSettings };
// Re-export types used by setup tabs
export type { Agent as GatewayAgent, ServiceCategory } from '$lib/api';

// Settings persistence (only global settings, not agents)
const DEFAULT_SETTINGS: GlobalSettings = {
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
let authenticated = $state(false);
let memories = $state<Memories>({ memory: '', user: '' });
let soul = $state<string>('');
let secrets = $state<Secret[]>([]);
let oauthTokens = $state<OAuthToken[]>([]);
let systemStatus = $state<SystemStatus>({ gateway_state: 'unknown', platforms: {} });
let channels = $state<ChannelDirectory>({ platforms: {} });
let analytics = $state<Analytics | null>(null);
let integrations = $state<Integration[]>([]);
let providers = $state<Provider[]>([]);
let relationships = $state<AgentRelationship[]>([]);
let owner = $state<OwnerProfile>({ name: 'Human' });
let connections = $state<Connection[]>([]);
let avatarCache = $state<Record<string, string>>({});
let pendingOps = $state(0);

/** Wrap any async operation to track in-flight state.
 *  Uses queueMicrotask to avoid mutating $state during $effect execution. */
async function tracked<T>(fn: () => Promise<T>): Promise<T> {
	queueMicrotask(() => pendingOps++);
	try { return await fn(); }
	finally { queueMicrotask(() => pendingOps--); }
}

const ws = createWsStore();

// Subscribe to WebSocket messages
ws.onMessage((msg: WsMessage) => {
	switch (msg.type) {
		case 'chunk':
			// Backend sends full accumulated text per chunk (edit semantics),
			// so replace rather than append to avoid duplication.
			streamingContent = msg.content ?? '';
			isStreaming = true;
			break;
		case 'message':
			if (isStreaming) {
				messages.push({
					id: msg.id ?? crypto.randomUUID(),
					role: 'assistant',
					content: renderMarkdown(streamingContent || msg.content || ''),
					timestamp: new Date().toISOString()
				});
				streamingContent = '';
				isStreaming = false;
			} else {
				messages.push({
					id: msg.id ?? crypto.randomUUID(),
					role: 'assistant',
					content: renderMarkdown(msg.content || ''),
					timestamp: new Date().toISOString()
				});
			}
			isTyping = false;
			break;
		case 'typing':
			isTyping = msg.active ?? false;
			break;
		case 'error':
			messages.push({
				id: msg.id ?? crypto.randomUUID(),
				role: 'assistant',
				content: renderMarkdown(msg.content || 'An error occurred.'),
				timestamp: new Date().toISOString()
			});
			isTyping = false;
			isStreaming = false;
			streamingContent = '';
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
	get avatarCache() { return avatarCache; },

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
	get isBusy() { return pendingOps > 0; },
	ws,

	async loadSessions() {
		await tracked(async () => {
			try {
				sessions = await api.listSessions(activeAgentId ?? undefined);
			} catch { sessions = []; }
		});
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
		isTyping = false;
		if (!id) {
			messages = [];
			ws.disconnect();
			return;
		}
		await tracked(async () => {
			try {
				const raw = await api.getHistory(id);
				messages = raw.map(m => m.role === 'assistant' ? { ...m, content: renderMarkdown(m.content) } : m);
			} catch { messages = []; }
			ws.connect(id);
		});
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

	sendMessage(content: string, meta?: Record<string, string>) {
		messages.push({
			id: crypto.randomUUID(),
			role: 'user',
			content,
			timestamp: new Date().toISOString()
		});
		ws.send(content, meta);
		isTyping = true;
	},

	async loadAgents() {
		await tracked(async () => {
			try {
				agents = await api.listAgents();
				if (!activeAgentId) {
					const saved = localStorage.getItem('vulti_active_agent');
					if (saved && agents.find(a => a.id === saved)) {
						activeAgentId = saved;
					} else if (agents.length > 0) {
						activeAgentId = agents[0].id;
					}
				}
				// Load avatar images in background
				for (const a of agents) {
					if (!avatarCache[a.id]) {
						api.getAgentAvatar(a.id).then(uri => {
							if (uri) avatarCache[a.id] = uri;
						}).catch(() => {});
					}
				}
			} catch { agents = []; }
		});
	},

	async createAgent(data: { name: string; role?: AgentRole; model?: string; avatar?: string; personality?: string; description?: string; inherit_from?: string }) {
		const agent = await api.createAgent(data);
		agents.push(agent);
		this.activeAgentId = agent.id;
		await this.reloadAgentResources();
		// Fire-and-forget Matrix onboarding (register, join global rooms, DM owner, send greeting)
		api.onboardAgentToMatrix(agent.id, agent.name).catch(() => {});
		return agent;
	},

	async updateAgent(agentId: string, updates: Partial<Agent>) {
		const agent = agents.find(a => a.id === agentId);
		if (agent) Object.assign(agent, updates);
		return tracked(async () => {
			const updated = await api.updateAgent(agentId, updates);
			if (agent) Object.assign(agent, updated);
			return updated;
		});
	},

	async deleteAgent(agentId: string) {
		agents = agents.filter(a => a.id !== agentId);
		relationships = relationships.filter(r => r.fromAgentId !== agentId && r.toAgentId !== agentId);
		if (activeAgentId === agentId) {
			this.activeAgentId = agents.length > 0 ? agents[0].id : null;
		}
		await tracked(async () => {
			await api.deleteAgent(agentId);
			if (activeAgentId) await this.reloadAgentResources();
		});
	},

	async markAgentReady(agentId: string) {
		await this.updateAgent(agentId, { status: 'ready' });
	},

	async addServiceToAgent(agentId: string, service: Partial<AgentService>) {
		const agent = agents.find(a => a.id === agentId);
		const newServices = [...(agent?.services ?? []), service as AgentService];
		if (agent) agent.services = newServices;
		await tracked(async () => {
			const updated = await api.updateAgent(agentId, { services: newServices } as Partial<Agent>);
			if (agent) Object.assign(agent, updated);
		});
	},

	async removeServiceFromAgent(agentId: string, serviceId: string) {
		const agent = agents.find(a => a.id === agentId);
		const filtered = agent?.services?.filter(s => s.id !== serviceId) ?? [];
		if (agent) agent.services = filtered;
		await tracked(async () => {
			const updated = await api.updateAgent(agentId, { services: filtered } as Partial<Agent>);
			if (agent) Object.assign(agent, updated);
		});
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
		isTyping = false;
		isStreaming = false;
		streamingContent = '';
		ws.disconnect();

		if (!activeAgentId) return;

		await tracked(() => Promise.all([
			this.loadSessions(),
			this.loadMemories(),
			this.loadSoul(),
			this.loadCron(),
		]));
	},

	async loadCron() {
		await tracked(async () => {
			try { cronJobs = await api.listCron(activeAgentId ?? undefined); } catch { cronJobs = []; }
		});
	},

	async createCronJob(data: Partial<CronJob>) {
		const tempId = crypto.randomUUID();
		const optimistic = { id: tempId, status: 'active', ...data } as CronJob;
		cronJobs.push(optimistic);
		await tracked(async () => {
			const created = await api.createCron(data, activeAgentId ?? undefined);
			const idx = cronJobs.findIndex(j => j.id === tempId);
			if (idx >= 0) cronJobs[idx] = created;
		});
	},

	async updateCronJob(id: string, updates: Partial<CronJob>) {
		const job = cronJobs.find(j => j.id === id);
		if (job) Object.assign(job, updates);
		await tracked(async () => {
			const updated = await api.updateCron(id, updates);
			if (job) Object.assign(job, updated);
		});
	},

	async deleteCronJob(id: string) {
		const idx = cronJobs.findIndex(j => j.id === id);
		if (idx >= 0) cronJobs.splice(idx, 1);
		await tracked(() => api.deleteCron(id));
	},

	async loadRules() {
		await tracked(async () => {
			try { rules = await api.listRules(activeAgentId ?? undefined); } catch { rules = []; }
		});
	},

	async createRule(data: Partial<Rule>) {
		const tempId = crypto.randomUUID();
		const optimistic = { id: tempId, enabled: true, trigger_count: 0, tags: [], ...data } as Rule;
		rules.push(optimistic);
		await tracked(async () => {
			const created = await api.createRule(data, activeAgentId ?? undefined);
			const idx = rules.findIndex(r => r.id === tempId);
			if (idx >= 0) rules[idx] = created;
		});
	},

	async updateRule(id: string, updates: Partial<Rule>) {
		const rule = rules.find(r => r.id === id);
		if (rule) Object.assign(rule, updates);
		await tracked(async () => {
			const updated = await api.updateRule(id, updates);
			if (rule) Object.assign(rule, updated);
		});
	},

	async deleteRule(id: string) {
		const idx = rules.findIndex(r => r.id === id);
		if (idx >= 0) rules.splice(idx, 1);
		await tracked(() => api.deleteRule(id));
	},

	async loadInbox() {
		try { inbox = await api.getInbox(); } catch { inbox = []; }
	},

	async loadContacts() {
		try { contacts = await api.getContacts(); } catch { contacts = []; }
	},

	async loadMemories() {
		await tracked(async () => {
			try { memories = await api.getMemories(activeAgentId ?? undefined); } catch { memories = { memory: '', user: '' }; }
		});
	},

	async saveMemory(file: 'memory' | 'user', content: string) {
		if (file === 'memory') memories = { ...memories, memory: content };
		else memories = { ...memories, user: content };
		await tracked(() => api.updateMemory(file, content, activeAgentId ?? undefined));
	},

	async loadSoul() {
		await tracked(async () => {
			try {
				const res = await api.getSoul(activeAgentId ?? undefined);
				soul = res.content;
			} catch { soul = ''; }
		});
	},

	async saveSoul(content: string) {
		soul = content;
		await tracked(() => api.updateSoul(content, activeAgentId ?? undefined));
	},

	async loadSecrets() {
		await tracked(async () => {
			try { secrets = await api.getSecrets(); } catch { secrets = []; }
		});
	},

	async loadOAuth() {
		await tracked(async () => {
			try { oauthTokens = await api.getOAuth(); } catch { oauthTokens = []; }
		});
	},

	async loadStatus() {
		await tracked(async () => {
			try { systemStatus = await api.getStatus(); } catch { systemStatus = { gateway_state: 'unknown', platforms: {} }; }
		});
	},

	async loadChannels() {
		await tracked(async () => {
			try { channels = await api.getChannels(); } catch { channels = { platforms: {} }; }
		});
	},

	async loadAnalytics(days: number = 30) {
		const agentId = store.activeAgentId || undefined;
		await tracked(async () => {
			try { analytics = await api.getAnalytics(days, agentId); } catch { analytics = null; }
		});
	},

	async loadIntegrations() {
		await tracked(async () => {
			try { integrations = await api.getIntegrations(); } catch { integrations = []; }
		});
	},

	// Providers (global intelligence)
	get providers() { return providers; },

	async loadProviders() {
		await tracked(async () => {
			try { providers = await api.getProviders(); } catch { providers = []; }
		});
	},

	// Connections
	get connections() { return connections; },

	async loadConnections() {
		await tracked(async () => {
			try { connections = await api.listConnections(); } catch { connections = []; }
		});
	},

	async addConnection(data: { name: string; connType: string; description: string; tags: string[]; credentials: Record<string, string>; mcp?: Record<string, unknown>; providesToolsets?: string[] }) {
		await tracked(async () => {
			const conn = await api.addConnection(data);
			connections = [...connections, conn];
		});
	},

	async updateConnection(name: string, updates: Record<string, unknown>) {
		await tracked(async () => {
			const updated = await api.updateConnection(name, updates);
			connections = connections.map(c => c.name === name ? updated : c);
		});
	},

	async deleteConnection(name: string) {
		connections = connections.filter(c => c.name !== name);
		await tracked(() => api.deleteConnection(name));
	},

	async updateAgentConnections(agentId: string, allowedConnections: string[]) {
		await this.updateAgent(agentId, { allowedConnections } as Partial<Agent>);
	},

	async addSecret(key: string, value: string) {
		await tracked(async () => {
			await api.addSecret(key, value);
			await Promise.all([this.loadProviders(), this.loadSecrets()]);
		});
	},

	async deleteSecret(key: string) {
		await tracked(async () => {
			await api.deleteSecret(key);
			await Promise.all([this.loadProviders(), this.loadSecrets()]);
		});
	},

	dismissNotification(index: number) {
		notifications = notifications.filter((_, i) => i !== index);
	},

	// Relationships
	get relationships() { return relationships; },

	async loadRelationships() {
		try { relationships = await api.listRelationships(); } catch { relationships = []; }
	},

	async createRelationship(fromId: string, toId: string, relType: 'manages' | 'collaborates') {
		const isOwnerFrom = fromId === 'owner';
		const isOwnerTo = toId === 'owner';

		const rel = await api.createRelationship(fromId, toId, relType);
		relationships = [...relationships, rel];

		if (isOwnerFrom || isOwnerTo) {
			// Owner-agent relationship: create DM, agent greets owner
			const agentId = isOwnerFrom ? toId : fromId;
			const agentName = agents.find(a => a.id === agentId)?.name || agentId;
			api.createOwnerDm(agentId, agentName).then(({ room_id }) => {
				if (room_id) {
					api.updateRelationship(rel.id, { matrixRoomId: room_id } as Partial<AgentRelationship>).catch(() => {});
					relationships = relationships.map(r =>
						r.id === rel.id ? { ...r, matrixRoomId: room_id } : r
					);
				}
			}).catch(() => {});
		} else if (relType === 'collaborates') {
			// Peer-peer: create "{Name} & {Name} Channel"
			const fromName = agents.find(a => a.id === fromId)?.name || fromId;
			const toName = agents.find(a => a.id === toId)?.name || toId;
			api.createRelationshipRoom(fromId, toId, relType, fromName, toName).then(({ room_id }) => {
				if (room_id) {
					api.updateRelationship(rel.id, { matrixRoomId: room_id } as Partial<AgentRelationship>).catch(() => {});
					relationships = relationships.map(r =>
						r.id === rel.id ? { ...r, matrixRoomId: room_id } : r
					);
				}
			}).catch(() => {});
		} else if (relType === 'manages') {
			// Hierarchical: managed agent joins the manager's team room
			// fromId = manager, toId = managed agent
			const managerId = fromId;
			const teamMembers = this._getTeamMembers(managerId);
			const managerName = agents.find(a => a.id === managerId)?.name || managerId;
			api.createSquadRoom(teamMembers, `${managerName}'s Team`).catch(() => {});
		}
		return rel;
	},

	/** Get all agent IDs in a manager's team (manager + all agents they manage). */
	_getTeamMembers(managerId: string): string[] {
		const members = [managerId];
		for (const r of relationships) {
			if (r.fromAgentId === managerId && r.type === 'manages' && !members.includes(r.toAgentId)) {
				members.push(r.toAgentId);
			}
		}
		return members;
	},

	async deleteRelationship(id: string) {
		await api.deleteRelationship(id);
		relationships = relationships.filter(r => r.id !== id);
	},

	// Owner
	get owner() { return owner; },

	async loadOwner() {
		try { owner = await api.getOwner(); } catch { owner = { name: 'Human' }; }
	},

	async updateOwner(name: string, avatar?: string, about?: string) {
		await tracked(async () => {
			owner = await api.updateOwner(name, avatar, about);
		});
	}
};
