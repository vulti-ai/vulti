<script lang="ts">
	import { onMount } from 'svelte';
	import { store } from '$lib/stores/app.svelte';
	import { computeLayout, type CanvasNode } from '$lib/canvas/layout';
	import CanvasNodeComponent from './canvas/CanvasNode.svelte';
	import CanvasEdge from './canvas/CanvasEdge.svelte';
	import SlideOutPanel from './SlideOutPanel.svelte';
	import GatewayStep from './setup/GatewayStep.svelte';

	let containerEl: HTMLDivElement | undefined = $state();
	let canvasWidth = $state(800);
	let canvasHeight = $state(600);

	// Panel state
	let panelMode = $state<'none' | 'agent' | 'owner' | 'settings' | 'create'>('none');
	let panelOpen = $derived(panelMode !== 'none');

	// Drag state
	let dragNodeId = $state<string | null>(null);
	let dragOffsets = $state<Record<string, { dx: number; dy: number }>>({});
	let mouseDownPos = $state<{ x: number; y: number } | null>(null);
	let hasMoved = $state(false);

	// Snap target while dragging
	let snapTargetId = $state<string | null>(null);

	// Spring animation
	let springAnimId: number | null = null;

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

	// Layout computation
	let layout = $derived(computeLayout(
		store.agents,
		store.relationships,
		store.owner,
		canvasWidth,
		canvasHeight
	));

	// Apply drag offsets to nodes for rendering
	let renderNodes = $derived(layout.nodes.map(n => {
		const off = dragOffsets[n.id];
		if (!off) return n;
		return { ...n, x: n.x + off.dx, y: n.y + off.dy };
	}));

	let nodeMap = $derived(new Map(renderNodes.map(n => [n.id, n])));

	// Context menu
	let contextMenu = $state<{ x: number; y: number; edgeId: string } | null>(null);

	onMount(() => {
		if (!containerEl) return;
		const ro = new ResizeObserver((entries) => {
			for (const entry of entries) {
				canvasWidth = entry.contentRect.width;
				canvasHeight = entry.contentRect.height;
			}
		});
		ro.observe(containerEl);
		return () => {
			ro.disconnect();
			if (springAnimId) cancelAnimationFrame(springAnimId);
		};
	});

	function svgCoords(e: MouseEvent): { x: number; y: number } {
		const svg = containerEl?.querySelector('svg');
		if (!svg) return { x: 0, y: 0 };
		const rect = svg.getBoundingClientRect();
		return {
			x: (e.clientX - rect.left) / rect.width * canvasWidth,
			y: (e.clientY - rect.top) / rect.height * canvasHeight,
		};
	}

	function handleNodeMouseDown(node: CanvasNode, e: MouseEvent) {
		if (node.type !== 'agent') return;
		e.preventDefault();
		mouseDownPos = { x: e.clientX, y: e.clientY };
		dragNodeId = node.id;
		hasMoved = false;
		snapTargetId = null;
		// Stop any running spring animation for this node
		if (dragOffsets[node.id]) {
			dragOffsets[node.id] = dragOffsets[node.id]; // keep current offset
		}
	}

	function handleMouseMove(e: MouseEvent) {
		if (!dragNodeId || !mouseDownPos) return;

		const dx = e.clientX - mouseDownPos.x;
		const dy = e.clientY - mouseDownPos.y;
		if (!hasMoved && Math.sqrt(dx * dx + dy * dy) < 5) return;
		hasMoved = true;

		// Update drag offset for this node
		const svgScale = canvasWidth / (containerEl?.querySelector('svg')?.getBoundingClientRect().width || canvasWidth);
		dragOffsets = {
			...dragOffsets,
			[dragNodeId]: { dx: dx * svgScale, dy: dy * svgScale }
		};

		// Check for snap targets
		const draggedNode = renderNodes.find(n => n.id === dragNodeId);
		if (!draggedNode) return;

		let closest: { id: string; dist: number } | null = null;
		for (const n of layout.nodes) {
			if (n.id === dragNodeId || n.type === 'owner' || n.type === 'add') continue;
			const ddx = draggedNode.x - n.x;
			const ddy = draggedNode.y - n.y;
			const dist = Math.sqrt(ddx * ddx + ddy * ddy);
			if (dist < 90 && (!closest || dist < closest.dist)) {
				closest = { id: n.id, dist };
			}
		}
		snapTargetId = closest?.id ?? null;
	}

	function handleMouseUp(_e: MouseEvent) {
		if (!dragNodeId) return;

		const nodeId = dragNodeId;
		const moved = hasMoved;

		if (moved && snapTargetId) {
			// Create relationship
			store.createRelationship(nodeId, snapTargetId, 'manages');
		}

		// Spring back animation
		if (moved) {
			startSpring(nodeId);
		}

		dragNodeId = null;
		mouseDownPos = null;
		snapTargetId = null;

		// If didn't move, treat as click
		if (!moved) {
			const node = layout.nodes.find(n => n.id === nodeId);
			if (node) handleNodeClick(node);
		}

		hasMoved = false;
	}

	function startSpring(nodeId: string) {
		const offset = dragOffsets[nodeId];
		if (!offset) return;

		let vx = 0;
		let vy = 0;
		let cx = offset.dx;
		let cy = offset.dy;

		const stiffness = 0.15;
		const damping = 0.7;

		function tick() {
			// Spring force toward origin
			const ax = -stiffness * cx;
			const ay = -stiffness * cy;
			vx = (vx + ax) * damping;
			vy = (vy + ay) * damping;
			cx += vx;
			cy += vy;

			if (Math.abs(cx) < 0.5 && Math.abs(cy) < 0.5 && Math.abs(vx) < 0.1 && Math.abs(vy) < 0.1) {
				// Settled
				const { [nodeId]: _, ...rest } = dragOffsets;
				dragOffsets = rest;
				return;
			}

			dragOffsets = { ...dragOffsets, [nodeId]: { dx: cx, dy: cy } };
			springAnimId = requestAnimationFrame(tick);
		}

		springAnimId = requestAnimationFrame(tick);
	}

	function handleNodeClick(node: CanvasNode) {
		contextMenu = null;
		if (node.type === 'owner') {
			panelMode = 'owner';
		} else if (node.type === 'add') {
			panelMode = 'create';
		} else {
			store.activeAgentId = node.id;
			store.reloadAgentResources();
			panelMode = 'agent';
		}
	}

	function handleEdgeContextMenu(edgeId: string, e: MouseEvent) {
		if (edgeId.startsWith('owner-')) return;
		contextMenu = { x: e.clientX, y: e.clientY, edgeId };
	}

	function deleteEdge() {
		if (contextMenu) {
			store.deleteRelationship(contextMenu.edgeId);
			contextMenu = null;
		}
	}

	function closePanel() {
		panelMode = 'none';
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={containerEl}
	class="relative h-full w-full overflow-hidden"
	onmousemove={handleMouseMove}
	onmouseup={handleMouseUp}
	onclick={() => { contextMenu = null; }}
>
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
			<button
				class="toolbar-btn"
				title="Settings"
				onclick={() => { panelMode = 'settings'; }}
			>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
					<path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
					<circle cx="12" cy="12" r="3"/>
				</svg>
			</button>
			<button
				class="toolbar-btn"
				title="Add Agent"
				onclick={() => { panelMode = 'create'; }}
			>
				<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
					<path d="M12 5v14M5 12h14" />
				</svg>
			</button>
		</div>

		<!-- SVG Canvas -->
		<svg viewBox="0 0 {canvasWidth} {canvasHeight}" class="h-full w-full">
			<!-- Edges -->
			{#each layout.edges as edge}
				{@const from = nodeMap.get(edge.fromId)}
				{@const to = nodeMap.get(edge.toId)}
				{#if from && to}
					<CanvasEdge
						fromNode={from}
						toNode={to}
						edgeId={edge.id}
						edgeType={edge.type}
						oncontextmenu={(e) => handleEdgeContextMenu(edge.id, e)}
					/>
				{/if}
			{/each}

			<!-- Drag preview: line from dragged node to cursor or snap target -->
			{#if dragNodeId && hasMoved}
				{@const draggedNode = nodeMap.get(dragNodeId)}
				{#if draggedNode}
					{#if snapTargetId}
						{@const target = nodeMap.get(snapTargetId)}
						{#if target}
							<!-- Snap preview line -->
							<line
								x1={draggedNode.x}
								y1={draggedNode.y}
								x2={target.x}
								y2={target.y}
								stroke="currentColor"
								stroke-width="2"
								opacity="0.3"
							/>
						{/if}
					{/if}
				{/if}
			{/if}

			<!-- Snap target highlight -->
			{#if snapTargetId}
				{@const target = nodeMap.get(snapTargetId)}
				{#if target}
					<rect
						x={target.x - 76}
						y={target.y - 34}
						width="152"
						height="68"
						rx="14"
						fill={target.color}
						opacity="0.1"
						class="pointer-events-none"
					/>
				{/if}
			{/if}

			<!-- Nodes -->
			{#each renderNodes.filter(n => n.type !== 'add') as node}
				<CanvasNodeComponent
					{node}
					selected={panelMode === 'agent' && store.activeAgentId === node.id
						|| panelMode === 'owner' && node.type === 'owner'}
					onclick={() => {
						if (!hasMoved) handleNodeClick(node);
					}}
					onmousedown={(e) => handleNodeMouseDown(node, e)}
				/>
			{/each}
		</svg>
	{/if}

	<!-- Full-screen panel -->
	{#if panelOpen && panelMode !== 'none'}
		<div class="panel-overlay" onclick={closePanel} onkeydown={() => {}}></div>
		<div class="panel-slide">
			<SlideOutPanel mode={panelMode} onclose={closePanel} />
		</div>
	{/if}

	<!-- Edge context menu -->
	{#if contextMenu}
		<div
			class="fixed z-50 rounded-lg border border-ink/8 bg-paper p-1 shadow-lg"
			style="left: {contextMenu.x}px; top: {contextMenu.y}px"
		>
			<button
				class="flex w-full items-center gap-2 rounded-md px-3 py-1.5 text-sm text-r-rose hover:bg-r-rose/10"
				onclick={deleteEdge}
			>
				Remove relationship
			</button>
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

	:global(html.light) .toolbar-btn {
		background: rgba(237, 231, 219, 0.7);
		color: #6B6460;
		border: 1px solid rgba(26, 26, 26, 0.06);
	}
	:global(html.light) .toolbar-btn:hover {
		background: rgba(237, 231, 219, 0.95);
		color: #3A3530;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
	}

	:global(html.dark) .toolbar-btn {
		background: rgba(38, 36, 34, 0.7);
		color: #9A938D;
		border: 1px solid rgba(255, 255, 255, 0.06);
	}
	:global(html.dark) .toolbar-btn:hover {
		background: rgba(38, 36, 34, 0.95);
		color: #E0DBD3;
		box-shadow: 0 2px 8px rgba(0, 0, 0, 0.2);
	}

	.panel-overlay {
		position: absolute;
		inset: 0;
		z-index: 30;
		backdrop-filter: blur(2px);
		-webkit-backdrop-filter: blur(2px);
	}

	:global(html.light) .panel-overlay {
		background: rgba(245, 240, 232, 0.3);
	}
	:global(html.dark) .panel-overlay {
		background: rgba(30, 28, 26, 0.4);
	}

	.panel-slide {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		z-index: 40;
		width: 100%;
		animation: slide-in 200ms ease-out;
	}

	@keyframes slide-in {
		from { transform: translateX(-24px); opacity: 0; }
		to { transform: translateX(0); opacity: 1; }
	}
</style>
