import { invoke } from '@tauri-apps/api/core';

const API_BASE = 'http://localhost:8080/api';

let authToken: string | null = null;

// Token is only needed for WebSocket connections and remaining HTTP calls
// (analytics, delete agent with Matrix cleanup, matrix registration).

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

// Lightweight cache only for remaining HTTP calls
const cache = new Map<string, { data: unknown; ts: number }>();
const CACHE_TTL = 30_000;

function getCached<T>(key: string): T | undefined {
	const entry = cache.get(key);
	if (entry && Date.now() - entry.ts < CACHE_TTL) return entry.data as T;
	return undefined;
}

export function invalidateCache(pattern?: string) {
	if (!pattern) { cache.clear(); return; }
	for (const key of cache.keys()) {
		if (key.includes(pattern)) cache.delete(key);
	}
}

// HTTP request helper — only used for endpoints that must stay on HTTP
async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
	const method = options.method?.toUpperCase() || 'GET';

	if (method === 'GET') {
		const cached = getCached<T>(path);
		if (cached !== undefined) return cached;
	}

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
	const data = await res.json();

	if (method === 'GET') {
		cache.set(path, { data, ts: Date.now() });
	} else {
		invalidateCache(path.split('/').slice(0, 3).join('/'));
	}

	return data;
}

export const api = {
	// === Tauri IPC calls (direct file I/O, sub-millisecond) ===

	// Agents
	listAgents() {
		return invoke<Agent[]>('list_agents');
	},
	getAgent(agentId: string) {
		return invoke<Agent>('get_agent', { agentId });
	},
	createAgent(data: { name: string; role?: AgentRole; model?: string; avatar?: string; personality?: string; description?: string; inherit_from?: string }) {
		return invoke<Agent>('create_agent', {
			name: data.name,
			role: data.role || null,
			avatar: data.avatar || null,
			description: data.description || null,
			personality: data.personality || null,
			model: data.model || null,
			inheritFrom: data.inherit_from || null,
		});
	},
	updateAgent(agentId: string, updates: Partial<Agent>) {
		return invoke<Agent>('update_agent', { agentId, updates });
	},
	finalizeOnboarding(agentId: string) {
		return invoke<{ role: string; agent: string }>('finalize_onboarding', { agentId });
	},
	getAgentAvatar(agentId: string) {
		return invoke<string | null>('get_agent_avatar', { agentId });
	},
	generateAgentAvatar(agentId: string) {
		return request(`/agents/${agentId}/generate-avatar`, { method: 'POST' });
	},
	saveWallet(agentId: string, wallet: WalletData) {
		return invoke<Wallet>('save_wallet', { agentId, wallet });
	},
	getWallet(agentId: string) {
		return invoke<Wallet>('get_wallet', { agentId });
	},
	createFastVault(name: string, email: string, password: string) {
		return invoke<string>('create_fast_vault', { name, email, password });
	},
	verifyFastVault(vaultId: string, code: string, agentId?: string) {
		return invoke<string>('verify_fast_vault', { vaultId, code, agentId: agentId || null });
	},
	resendVaultVerification(vaultId: string, email: string, password: string) {
		return invoke<boolean>('resend_vault_verification', { vaultId, email, password });
	},
	ensureVultisig() {
		return invoke<string>('ensure_vultisig');
	},
	getAgentVault(agentId: string) {
		return invoke<{ name: string; vault_id: string; file: string } | null>('get_agent_vault', { agentId });
	},
	deleteAgentVault(agentId: string) {
		return invoke<void>('delete_agent_vault', { agentId });
	},
	vaultAddresses(vaultId: string) {
		return invoke<Record<string, unknown>>('vault_addresses', { vaultId });
	},
	vaultBalance(vaultId: string, chain?: string, includeTokens?: boolean) {
		return invoke<Record<string, unknown>>('vault_balance', { vaultId, chain: chain || null, includeTokens: includeTokens || null });
	},
	vaultSend(vaultId: string, chain: string, to: string, password: string, opts?: { amount?: string; token?: string; max?: boolean; memo?: string }) {
		return invoke<Record<string, unknown>>('vault_send', { vaultId, chain, to, password, amount: opts?.amount || null, token: opts?.token || null, max: opts?.max || null, memo: opts?.memo || null });
	},
	vaultSwap(vaultId: string, fromChain: string, toChain: string, password: string, opts?: { amount?: string; max?: boolean }) {
		return invoke<Record<string, unknown>>('vault_swap', { vaultId, fromChain, toChain, password, amount: opts?.amount || null, max: opts?.max || null });
	},
	vaultSwapQuote(vaultId: string, fromChain: string, toChain: string, amount?: string) {
		return invoke<Record<string, unknown>>('vault_swap_quote', { vaultId, fromChain, toChain, amount: amount || null });
	},
	vaultPortfolio(vaultId: string) {
		return invoke<Record<string, unknown>>('vault_portfolio', { vaultId });
	},

	// Sessions
	listSessions(agentId?: string) {
		return invoke<Session[]>('list_sessions', { agentId: agentId || null });
	},
	createSession(agentId?: string, name?: string) {
		return invoke<Session>('create_session', { agentId: agentId || null, name: name || null });
	},
	deleteSession(id: string) {
		return invoke<{ ok: boolean }>('delete_session', { sessionId: id });
	},
	getHistory(sessionId: string) {
		return invoke<Message[]>('get_history', { sessionId });
	},

	// Memories & Soul
	getMemories(agentId?: string) {
		return invoke<Memories>('get_memories', { agentId: agentId || null });
	},
	updateMemory(file: 'memory' | 'user', content: string, agentId?: string) {
		return invoke<{ ok: boolean }>('update_memory', { agentId: agentId || null, file, content });
	},
	getSoul(agentId?: string) {
		return invoke<{ content: string }>('get_soul', { agentId: agentId || null });
	},
	updateSoul(content: string, agentId?: string) {
		return invoke<{ ok: boolean }>('update_soul', { agentId: agentId || null, content });
	},

	// Rules
	listRules(agentId?: string) {
		return invoke<Rule[]>('list_rules', { agentId: agentId || null });
	},
	createRule(rule: Partial<Rule>, agentId?: string) {
		return invoke<Rule>('create_rule', { data: rule, agentId: agentId || null });
	},
	updateRule(id: string, updates: Partial<Rule>) {
		return invoke<Rule>('update_rule', { ruleId: id, updates });
	},
	deleteRule(id: string) {
		return invoke<void>('delete_rule', { ruleId: id });
	},

	// Cron
	listCron(agentId?: string) {
		return invoke<CronJob[]>('list_cron', { agentId: agentId || null });
	},
	createCron(job: Partial<CronJob>, agentId?: string) {
		return invoke<CronJob>('create_cron', { data: job, agentId: agentId || null });
	},
	updateCron(id: string, updates: Partial<CronJob>) {
		return invoke<CronJob>('update_cron', { jobId: id, updates });
	},
	deleteCron(id: string) {
		return invoke<void>('delete_cron', { jobId: id });
	},

	// Secrets & Providers
	getSecrets() {
		return invoke<Secret[]>('list_secrets');
	},
	addSecret(key: string, value: string) {
		return invoke<{ ok: boolean }>('add_secret', { key, value });
	},
	deleteSecret(key: string) {
		return invoke<{ ok: boolean }>('delete_secret', { key });
	},
	getProviders() {
		return invoke<Provider[]>('list_providers');
	},
	getOAuth() {
		return invoke<OAuthToken[]>('get_oauth_status');
	},

	// Connections
	listConnections() {
		return invoke<Connection[]>('list_connections');
	},
	addConnection(data: { name: string; connType: string; description: string; tags: string[]; credentials: Record<string, string>; mcp?: Record<string, unknown>; providesToolsets?: string[] }) {
		return invoke<Connection>('add_connection', data);
	},
	updateConnection(name: string, updates: Record<string, unknown>) {
		return invoke<Connection>('update_connection', { name, updates });
	},
	deleteConnection(name: string) {
		return invoke<{ ok: boolean }>('delete_connection', { name });
	},

	// Status & Config
	getStatus() {
		return invoke<SystemStatus>('get_system_status');
	},
	getChannels() {
		return invoke<ChannelDirectory>('get_channel_directory');
	},
	getIntegrations() {
		return invoke<Integration[]>('get_integrations');
	},

	// Relationships
	listRelationships() {
		return invoke<AgentRelationship[]>('list_relationships');
	},
	createRelationship(fromId: string, toId: string, relType: string) {
		return invoke<AgentRelationship>('create_relationship', { fromId, toId, relType });
	},
	deleteRelationship(relId: string) {
		return invoke<{ ok: boolean }>('delete_relationship', { relId });
	},
	updateRelationship(relId: string, updates: Partial<AgentRelationship>) {
		return invoke<AgentRelationship>('update_relationship', { relId, updates });
	},

	// Skills
	listAvailableSkills() {
		return invoke<Skill[]>('list_available_skills');
	},
	listAgentSkills(agentId: string) {
		return invoke<Skill[]>('list_agent_skills', { agentId });
	},
	installAgentSkill(agentId: string, skillName: string) {
		return invoke<Skill>('install_agent_skill', { agentId, skillName });
	},
	removeAgentSkill(agentId: string, skillName: string) {
		return invoke<void>('remove_agent_skill', { agentId, skillName });
	},

	// Config Versioning
	listConfigRevisions(agentId: string) {
		return invoke<ConfigRevision[]>('list_config_revisions', { agentId });
	},
	getConfigRevision(agentId: string, revision: string) {
		return invoke<string>('get_config_revision', { agentId, revision });
	},
	rollbackConfig(agentId: string, revision: string) {
		return invoke<void>('rollback_config', { agentId, revision });
	},

	// Approvals
	listApprovals(agentId?: string) {
		return invoke<ApprovalRequest[]>('list_approvals', { agentId: agentId || null });
	},
	resolveApproval(approvalId: string, approved: boolean) {
		return invoke<ApprovalRequest>('resolve_approval', { approvalId, approved });
	},

	// Pane Widgets
	getPaneWidgets(agentId: string) {
		return invoke<PaneWidgets>('get_pane_widgets', { agentId });
	},
	clearPaneWidgets(agentId: string, tab?: string) {
		return invoke<void>('clear_pane_widgets', { agentId, tab: tab || null });
	},

	// Audit
	listAuditEvents(n?: number, agentId?: string, traceId?: string, eventType?: string) {
		return invoke<AuditEvent[]>('list_audit_events', {
			n: n || 50,
			agentId: agentId || null,
			traceId: traceId || null,
			eventType: eventType || null,
		});
	},

	// Owner
	getOwner() {
		return invoke<OwnerProfile>('get_owner');
	},
	updateOwner(name: string, avatar?: string | null, about?: string | null) {
		return invoke<OwnerProfile>('update_owner', { name, avatar: avatar || null, about: about || null });
	},

	// Matrix operations (HTTP — needs running gateway)
	createRelationshipRoom(fromAgentId: string, toAgentId: string, relType: string, fromAgentName?: string, toAgentName?: string) {
		return request<{ room_id: string }>('/matrix/relationship-room', {
			method: 'POST',
			body: JSON.stringify({ from_agent_id: fromAgentId, to_agent_id: toAgentId, rel_type: relType, from_agent_name: fromAgentName || '', to_agent_name: toAgentName || '' })
		});
	},

	resetMatrixRooms() {
		return request<{ rooms_deleted: number; rooms_created: Record<string, unknown> }>('/matrix/reset-rooms', {
			method: 'POST'
		});
	},

	createOwnerDm(agentId: string, agentName: string) {
		return request<{ room_id: string }>('/matrix/owner-dm', {
			method: 'POST',
			body: JSON.stringify({ agent_id: agentId, agent_name: agentName })
		});
	},

	onboardAgentToMatrix(agentId: string, agentName: string) {
		return request<{ matrix_user_id: string | null; dm_room_id: string | null }>('/matrix/onboard-agent', {
			method: 'POST',
			body: JSON.stringify({ agent_id: agentId, agent_name: agentName })
		});
	},

	createSquadRoom(agentIds: string[], squadName: string, topic?: string) {
		return request<{ room_id: string }>('/matrix/squad-room', {
			method: 'POST',
			body: JSON.stringify({ agent_ids: agentIds, squad_name: squadName, topic: topic || '' })
		});
	},

	addAgentToRoom(roomId: string, agentId: string, inviterAgentId?: string) {
		return request<{ ok: boolean }>(`/matrix/rooms/${encodeURIComponent(roomId)}/members`, {
			method: 'POST',
			body: JSON.stringify({ agent_id: agentId, inviter_agent_id: inviterAgentId || '' })
		});
	},

	removeAgentFromRoom(roomId: string, agentId: string) {
		return request<{ ok: boolean }>(`/matrix/rooms/${encodeURIComponent(roomId)}/members/${encodeURIComponent(agentId)}`, {
			method: 'DELETE'
		});
	},

	// === HTTP calls (still need running gateway) ===

	// Auth (remote access only)
	auth(token: string) {
		return request<{ ok: boolean }>('/auth', {
			method: 'POST',
			body: JSON.stringify({ token })
		});
	},

	// Delete agent (needs Matrix cleanup via gateway)
	deleteAgent(agentId: string) {
		return request<{ ok: boolean }>(`/agents/${agentId}`, { method: 'DELETE' });
	},

	// Inbox & Contacts (low priority, keep HTTP)
	getInbox() {
		return request<InboxItem[]>('/inbox');
	},
	getContacts() {
		return request<Contact[]>('/contacts');
	},

	// Matrix registration (needs gateway for homeserver API)
	registerMatrixOwner(username: string, password: string, displayName: string) {
		return request<{ user_id: string; username: string }>('/matrix/register', {
			method: 'POST',
			body: JSON.stringify({ username, password, display_name: displayName })
		});
	},

	// Analytics (direct SQLite via Tauri IPC)
	getAnalytics(days: number = 30, agentId?: string) {
		return invoke<Analytics>('get_analytics', { days, agentId: agentId || null });
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

export type AgentRole = 'assistant' | 'therapist' | 'researcher' | 'engineer' | 'writer' | 'analyst' | 'coach' | 'creative' | 'ops';

// Unified Agent type (merges old Agent + GatewayAgent)
export interface Agent {
	id: string;
	name: string;
	role?: AgentRole;
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
	allowedConnections?: string[];
	isDefault?: boolean;
}

export interface Connection {
	name: string;
	type: string;
	description: string;
	tags: string[];
	credentials: Record<string, string>;
	mcp: Record<string, unknown>;
	providesToolsets: string[];
	enabled: boolean;
}

export interface CronJob {
	id: string;
	name: string;
	prompt: string;
	schedule: string;
	status: 'active' | 'paused';
	last_run?: string;
	last_output?: string;
	persist_session?: boolean;
	max_session_turns?: number;
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

export interface Provider {
	id: string;
	name: string;
	authenticated: boolean;
	models: string[];
	env_keys: string[];
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
	permission?: 'read' | 'write';
}

// Keep GatewayAgent as alias for backward compat
export type GatewayAgent = Agent;

export interface AgentRelationship {
	id: string;
	fromAgentId: string;
	toAgentId: string;
	type: 'manages' | 'collaborates';
	matrixRoomId?: string;
	createdAt: string;
}

export interface CreditCard {
	name: string;
	number: string;
	expiry: string;
	code: string;
}

export interface CryptoWallet {
	vaultId: string;
	name: string;
	email: string;
}

export interface CryptoWalletData {
	vault_id: string;
	name: string;
	email: string;
}

export interface WalletData {
	credit_card?: CreditCard;
	crypto?: CryptoWalletData;
}

export interface Wallet {
	creditCard?: CreditCard;
	crypto?: CryptoWallet;
}

export interface OwnerProfile {
	name: string;
	avatar?: string;
	about?: string;
}

export interface GlobalSettings {
	gateway: { connected: boolean };
}

export interface GatewayState {
	global: GlobalSettings;
	agents: Agent[];
	activeAgentId: string | null;
}

export type WidgetType = 'markdown' | 'kv' | 'table' | 'image' | 'status' | 'stat_grid' | 'bar_chart' | 'progress' | 'button' | 'form' | 'toggle_list' | 'action_list' | 'empty';

export interface Widget {
	id: string;
	type: WidgetType;
	title?: string;
	// eslint-disable-next-line @typescript-eslint/no-explicit-any
	data: Record<string, any>;
}

export interface PaneWidgets {
	version: number;
	tabs: Record<string, Widget[]>;
}

export interface Skill {
	name: string;
	description: string;
	category: string;
	installed: boolean;
}

export interface ConfigRevision {
	revision: string;
	timestamp: string;
	size: number;
}

export interface ApprovalRequest {
	id: string;
	agent_id: string;
	action_type: string;
	description: string;
	details: Record<string, unknown>;
	status: 'pending' | 'approved' | 'denied' | 'expired';
	created_at: string;
	expires_at: string;
	resolved_at?: string;
	resolved_by?: string;
}

export interface AuditEvent {
	ts: string;
	event: string;
	agent_id: string;
	trace_id?: string;
	details?: Record<string, unknown>;
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
