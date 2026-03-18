<script lang="ts">
	import type { CanvasNode } from '$lib/canvas/layout';

	let { node, selected = false, onclick, onmousedown }: {
		node: CanvasNode;
		selected?: boolean;
		onclick?: () => void;
		onmousedown?: (e: MouseEvent) => void;
	} = $props();

	function statusColor(status?: string): string {
		if (!status) return '#9A938D';
		if (['connected', 'active', 'ready'].includes(status)) return '#8BC867';
		if (['disconnected', 'stopped', 'setting_up'].includes(status)) return '#F0A84A';
		return '#E8607A';
	}

	// Use theme-appropriate colors
	const nodeWidth = 140;
	const nodeHeight = 56;
	const ownerRadius = 40;
</script>

{#if node.type === 'owner'}
	<g
		transform="translate({node.x},{node.y})"
		class="cursor-pointer"
		role="button"
		tabindex="0"
		{onclick}
		onkeydown={(e) => e.key === 'Enter' && onclick?.()}
	>
		<!-- Outer glow on select -->
		{#if selected}
			<circle r={ownerRadius + 6} fill="none" stroke={node.color} stroke-width="1" opacity="0.2" />
		{/if}
		<!-- Main circle -->
		<circle
			r={ownerRadius}
			fill="none"
			stroke={node.color}
			stroke-width={selected ? 2.5 : 1.5}
			opacity="0.8"
		/>
		<!-- Inner subtle fill -->
		<circle r={ownerRadius} fill={node.color} opacity="0.06" />
		<!-- Name -->
		<text
			text-anchor="middle"
			dy="-2"
			fill="currentColor"
			font-size="15"
			font-weight="600"
			class="select-none"
		>{node.label}</text>
		<!-- Role -->
		<text
			text-anchor="middle"
			dy="16"
			fill={node.color}
			font-size="11"
			font-weight="400"
			class="select-none"
		>{node.sublabel}</text>
	</g>

{:else if node.type === 'add'}
	<!-- Handled outside SVG now -->

{:else}
	<g
		transform="translate({node.x},{node.y})"
		class="cursor-pointer"
		role="button"
		tabindex="0"
		{onclick}
		onmousedown={(e) => onmousedown?.(e)}
		onkeydown={(e) => e.key === 'Enter' && onclick?.()}
	>
		<!-- Selection glow -->
		{#if selected}
			<rect
				x={-nodeWidth / 2 - 4}
				y={-nodeHeight / 2 - 4}
				width={nodeWidth + 8}
				height={nodeHeight + 8}
				rx="14"
				fill="none"
				stroke={node.color}
				stroke-width="1"
				opacity="0.2"
			/>
		{/if}
		<!-- Fill -->
		<rect
			x={-nodeWidth / 2}
			y={-nodeHeight / 2}
			width={nodeWidth}
			height={nodeHeight}
			rx="10"
			fill={node.color}
			opacity="0.06"
		/>
		<!-- Border -->
		<rect
			x={-nodeWidth / 2}
			y={-nodeHeight / 2}
			width={nodeWidth}
			height={nodeHeight}
			rx="10"
			fill="none"
			stroke={node.color}
			stroke-width={selected ? 2 : 1}
			opacity={selected ? 0.9 : 0.5}
		/>
		<!-- Name -->
		<text
			text-anchor="middle"
			dy={node.sublabel ? '-3' : '4'}
			fill="currentColor"
			font-size="14"
			font-weight="500"
			class="select-none"
		>{node.label}</text>
		<!-- Role -->
		{#if node.sublabel}
			<text
				text-anchor="middle"
				dy="15"
				fill={node.color}
				font-size="11"
				font-weight="400"
				class="select-none"
			>{node.sublabel}</text>
		{/if}
		<!-- Status dot -->
		<circle
			cx={nodeWidth / 2 - 10}
			cy={-nodeHeight / 2 + 10}
			r="4"
			fill={statusColor(node.status)}
		/>
	</g>
{/if}
