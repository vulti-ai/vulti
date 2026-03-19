import type { Agent, AgentRelationship, OwnerProfile } from '$lib/api';

export interface CanvasNode {
	id: string;
	type: 'owner' | 'agent' | 'add';
	x: number;
	y: number;
	label: string;
	sublabel: string;
	color: string;
	status?: string;
	role?: string;
}

export interface CanvasEdge {
	id: string;
	fromId: string;
	toId: string;
	type: string;
}

// Colors pulled from the rainbow paper theme
const ROLE_COLORS: Record<string, string> = {
	// Blue family — coordination roles
	assistant: '#6B8BEB',
	ops: '#6B8BEB',
	analyst: '#5AADE0',
	// Green family — technical roles
	engineer: '#8BC867',
	researcher: '#4AC6B7',
	// Warm family — people roles
	therapist: '#F28B6D',
	coach: '#F0A84A',
	creative: '#D96BA8',
	writer: '#E8607A',
};

const OWNER_COLOR = '#E8607A';
const DEFAULT_COLOR = '#9D7AEA';

function roleColor(role?: string): string {
	if (!role) return DEFAULT_COLOR;
	return ROLE_COLORS[role] || DEFAULT_COLOR;
}

export function computeLayout(
	agents: Agent[],
	relationships: AgentRelationship[],
	owner: OwnerProfile,
	width: number,
	height: number
): { nodes: CanvasNode[]; edges: CanvasEdge[] } {
	if (width < 100 || height < 100) {
		return { nodes: [], edges: [] };
	}

	const nodes: CanvasNode[] = [];
	const edges: CanvasEdge[] = [];

	// Owner node at top center, with generous top margin
	const topMargin = Math.min(height * 0.15, 120);
	const ownerNode: CanvasNode = {
		id: '__owner__',
		type: 'owner',
		x: width / 2,
		y: topMargin,
		label: owner.name || 'Human',
		sublabel: 'Human',
		color: OWNER_COLOR,
	};
	nodes.push(ownerNode);

	if (agents.length === 0) {
		return { nodes, edges };
	}

	// Build adjacency: who manages whom (skip owner — it's not an agent node)
	const managedBy = new Map<string, string>();
	const agentIds = new Set(agents.map(a => a.id));
	const managesRelationships = relationships.filter(r => r.type === 'manages');
	for (const rel of managesRelationships) {
		if (agentIds.has(rel.fromAgentId)) {
			managedBy.set(rel.toAgentId, rel.fromAgentId);
		}
	}

	// Compute depth for each agent
	const agentDepth = new Map<string, number>();

	function getDepth(agentId: string, visited: Set<string>): number {
		if (agentDepth.has(agentId)) return agentDepth.get(agentId)!;
		if (visited.has(agentId)) return 1;
		visited.add(agentId);

		const parent = managedBy.get(agentId);
		if (!parent) {
			agentDepth.set(agentId, 1);
			return 1;
		}
		const parentDepth = getDepth(parent, visited);
		const depth = parentDepth + 1;
		agentDepth.set(agentId, depth);
		return depth;
	}

	for (const agent of agents) {
		getDepth(agent.id, new Set());
	}

	// Group agents by depth
	const depthGroups = new Map<number, Agent[]>();
	for (const agent of agents) {
		const d = agentDepth.get(agent.id) || 1;
		if (!depthGroups.has(d)) depthGroups.set(d, []);
		depthGroups.get(d)!.push(agent);
	}

	const maxDepth = Math.max(...depthGroups.keys(), 1);

	// Dynamic vertical spacing — breathe more with fewer levels
	const availableHeight = height - topMargin - 80;
	const verticalSpacing = Math.min(180, availableHeight / (maxDepth + 0.5));

	// Place agent nodes — center each depth row, with padding from edges
	const horizontalPadding = 100;
	const usableWidth = width - horizontalPadding * 2;

	for (const [depth, group] of depthGroups) {
		const y = topMargin + depth * verticalSpacing;
		const count = group.length;
		const spacing = Math.min(220, usableWidth / count);
		const rowWidth = spacing * (count - 1);
		const startX = width / 2 - rowWidth / 2;

		for (let i = 0; i < count; i++) {
			const x = count === 1 ? width / 2 : startX + i * spacing;
			const agent = group[i];
			nodes.push({
				id: agent.id,
				type: 'agent',
				x,
				y,
				label: agent.name,
				sublabel: agent.role || '',
				color: roleColor(agent.role),
				status: agent.status,
				role: agent.role,
			});
		}
	}

	// Implicit edges: owner -> all depth-1 agents
	for (const agent of depthGroups.get(1) || []) {
		edges.push({
			id: `owner-${agent.id}`,
			fromId: '__owner__',
			toId: agent.id,
			type: 'manages',
		});
	}

	// Explicit edges from relationships
	const nodeIds = new Set(nodes.map(n => n.id));
	for (const rel of relationships) {
		// Map "owner" to "__owner__"
		const fromId = rel.fromAgentId === 'owner' ? '__owner__' : rel.fromAgentId;
		const toId = rel.toAgentId === 'owner' ? '__owner__' : rel.toAgentId;

		// Skip if either node doesn't exist
		if (!nodeIds.has(fromId) || !nodeIds.has(toId)) continue;
		// Skip if this duplicates an implicit owner edge
		if (fromId === '__owner__' && agentDepth.get(rel.toAgentId) === 1) continue;

		edges.push({
			id: rel.id,
			fromId,
			toId,
			type: rel.type,
		});
	}

	return { nodes, edges };
}
