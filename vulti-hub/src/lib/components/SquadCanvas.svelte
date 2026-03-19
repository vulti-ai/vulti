<script lang="ts">
	import { onMount } from 'svelte';
	import { SvelteFlow, Background, BackgroundVariant, type Node, type Edge, type Connection, Position, MarkerType } from '@xyflow/svelte';
	import '@xyflow/svelte/dist/style.css';
	import { store } from '$lib/stores/app.svelte';
	import { computeLayout } from '$lib/canvas/layout';
	import AgentNode from './canvas/AgentNode.svelte';
	import OwnerNode from './canvas/OwnerNode.svelte';
	import DeletableEdge from './canvas/DeletableEdge.svelte';
	import SlideOutPanel from './SlideOutPanel.svelte';
	import GatewayStep from './setup/GatewayStep.svelte';

	const nodeTypes = { agent: AgentNode, owner: OwnerNode };
	const edgeTypes = { deletable: DeletableEdge };

	function handleEdgeDelete(edgeId: string) {
		if (edgeId.startsWith('owner-')) return;
		store.deleteRelationship(edgeId);
	}

	// Panel
	let panelMode = $state<'none' | 'agent' | 'owner' | 'settings' | 'create' | 'onboard' | 'audit'>('none');
	let panelOpen = $derived(panelMode !== 'none');

	let gatewayConnected = $derived(store.gatewayGlobal.gateway?.connected);

	$effect(() => {
		if (gatewayConnected) {
			store.loadAgents();
			store.loadRelationships();
			store.loadOwner();
		}
	});

	$effect(() => {
		if (store.activeAgentId && panelMode === 'agent') {
			store.loadStatus();
			store.loadIntegrations();
			store.loadMemories();
			store.loadSoul();
			store.loadCron();
			store.loadRules();
			store.loadAnalytics();
			store.loadSecrets();
			store.loadOAuth();
			store.loadChannels();
		}
	});

	// Convert layout to Svelte Flow nodes/edges
	let layout = $derived(computeLayout(
		store.agents, store.relationships, store.owner, 900, 600
	));

	let flowNodes = $state<Node[]>([]);
	let flowEdges = $state<Edge[]>([]);

	$effect(() => {
		flowNodes = layout.nodes
			.filter(n => n.type !== 'add')
			.map(n => ({
				id: n.id,
				type: n.type === 'owner' ? 'owner' : 'agent',
				position: { x: n.x - (n.type === 'owner' ? 40 : 70), y: n.y - (n.type === 'owner' ? 40 : 28) },
				data: { label: n.label, sublabel: n.sublabel, color: n.color, status: n.status, avatarUri: n.type === 'agent' ? store.avatarCache[n.id] : undefined },
				draggable: n.type !== 'owner',
				sourcePosition: Position.Bottom,
				targetPosition: Position.Top,
			}));

		flowEdges = layout.edges.map(e => {
			const isImplicit = e.id.startsWith('owner-');
			return {
				id: e.id,
				source: e.fromId,
				target: e.toId,
				type: 'deletable',
				animated: false,
				markerEnd: { type: MarkerType.ArrowClosed, width: 16, height: 12 },
				style: 'stroke-width: 1.5; opacity: 0.25;',
				data: { deletable: !isImplicit, ondelete: handleEdgeDelete },
			};
		});
	});

	function onBeforeConnect(connection: Connection): Connection | false | null {
		const src = connection.source;
		const tgt = connection.target;
		if (!src || !tgt) return false;
		if (src === tgt) return false;
		// Don't allow connecting TO the owner (owner is always source)
		if (tgt === '__owner__') return false;

		// Map owner node id
		const fromId = src === '__owner__' ? 'owner' : src;
		const toId = tgt;

		store.createRelationship(fromId, toId, 'manages');
		// Return false — we manage edges ourselves via the store
		return false;
	}

	function onNodeClick({ node }: { node: Node; event: MouseEvent | TouchEvent }) {
		if (node.type === 'owner') {
			panelMode = 'owner';
		} else {
			store.activeAgentId = node.id;
			store.reloadAgentResources();
			panelMode = 'agent';
		}
	}

	function closePanel() { panelMode = 'none'; }

	// Force SvelteFlow to re-mount (and re-fitView) when node count changes
	let flowKey = $derived(`flow-${flowNodes.length}`);
</script>

<div class="relative h-full w-full">
	{#if !gatewayConnected}
		<div class="absolute inset-0 z-20 flex items-center justify-center bg-paper/80 backdrop-blur-sm">
			<div class="w-full max-w-md">
				<GatewayStep
					status="pending"
					onComplete={() => { store.updateGlobalSettings({ gateway: { connected: true } }); }}
				/>
			</div>
		</div>
	{:else}
		<!-- Left toolbar -->
		<div class="absolute left-5 top-5 z-10 flex flex-col gap-2">
			<button class="toolbar-btn" title="Settings" onclick={() => { panelMode = 'settings'; }}>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
					<circle cx="12" cy="12" r="3"/>
				</svg>
			</button>
			<button class="toolbar-btn" title="Add Agent" onclick={() => { panelMode = 'create'; }}>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
					<path d="M12 5v14M5 12h14" />
				</svg>
			</button>
			<button class="toolbar-btn" title="Audit Log" onclick={() => { panelMode = 'audit'; }}>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M12 8v4l3 3" />
					<circle cx="12" cy="12" r="9" />
				</svg>
			</button>
		</div>

		<div class="h-full w-full flow-container">
			{#key flowKey}
			<SvelteFlow
				nodes={flowNodes}
				edges={flowEdges}
				{nodeTypes}
				{edgeTypes}
				onbeforeconnect={onBeforeConnect}
				onnodeclick={onNodeClick}
				fitView
				fitViewOptions={{ padding: 0.2 }}
				connectionRadius={40}
				proOptions={{ hideAttribution: true }}
			>
				<Background variant={BackgroundVariant.Dots} gap={24} size={1} />
			</SvelteFlow>
			{/key}
		</div>
	{/if}

	<!-- Full-screen panel -->
	{#if panelOpen && panelMode !== 'none'}
		<div class="panel-overlay" onclick={closePanel} onkeydown={() => {}}></div>
		<div class="panel-slide">
			<SlideOutPanel mode={panelMode} onclose={closePanel} onmodechange={(m) => panelMode = m as typeof panelMode} />
		</div>
	{/if}
</div>

<style>
	.toolbar-btn {
		display: flex;
		align-items: center;
		justify-content: center;
		width: 36px;
		height: 36px;
		border-radius: 10px;
		transition: all 150ms ease;
	}
	:global(html.light) .toolbar-btn { background: rgba(237, 231, 219, 0.7); color: #6B6460; border: 1px solid rgba(26, 26, 26, 0.06); }
	:global(html.light) .toolbar-btn:hover { background: rgba(237, 231, 219, 0.95); color: #3A3530; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06); }
	:global(html.dark) .toolbar-btn { background: rgba(38, 36, 34, 0.7); color: #9A938D; border: 1px solid rgba(255, 255, 255, 0.06); }
	:global(html.dark) .toolbar-btn:hover { background: rgba(38, 36, 34, 0.95); color: #E0DBD3; box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2); }

	.panel-overlay { position: absolute; inset: 0; z-index: 30; backdrop-filter: blur(2px); -webkit-backdrop-filter: blur(2px); }
	:global(html.light) .panel-overlay { background: rgba(245, 240, 232, 0.3); }
	:global(html.dark) .panel-overlay { background: rgba(30, 28, 26, 0.4); }

	.panel-slide { position: absolute; left: 0; top: 0; bottom: 0; z-index: 40; width: 100%; animation: slide-in 200ms ease-out; }
	@keyframes slide-in { from { transform: translateX(-24px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }

	/* Override Svelte Flow defaults to match our theme */
	:global(.flow-container .svelte-flow) {
		background: transparent !important;
	}
	:global(.flow-container .svelte-flow__background) {
		opacity: 0.3;
	}
	:global(.flow-container .svelte-flow__handle) {
		width: 8px;
		height: 8px;
		border-radius: 50%;
		border: 1.5px solid;
		opacity: 0;
		transition: opacity 150ms ease;
	}
	:global(.flow-container .svelte-flow__node:hover .svelte-flow__handle) {
		opacity: 0.6;
	}
	:global(.flow-container .svelte-flow__handle.connecting) {
		opacity: 1;
	}
	:global(html.light .flow-container .svelte-flow__handle) {
		background: #EDE7DB;
		border-color: #9A938D;
	}
	:global(html.dark .flow-container .svelte-flow__handle) {
		background: #302D2A;
		border-color: #6B6460;
	}
	:global(.flow-container .svelte-flow__edge-path) {
		stroke: currentColor;
	}
	:global(.flow-container .svelte-flow__connection-path) {
		stroke: currentColor;
		opacity: 0.3;
	}
	:global(.flow-container .svelte-flow__node) {
		cursor: pointer;
	}
	/* Hide Svelte Flow attribution if proOptions doesn't work */
	:global(.flow-container .svelte-flow__attribution) {
		display: none;
	}
	/* Remove default node styling */
	:global(.flow-container .svelte-flow__node-agent),
	:global(.flow-container .svelte-flow__node-owner) {
		background: none;
		border: none;
		padding: 0;
		border-radius: 0;
		box-shadow: none;
	}
</style>
