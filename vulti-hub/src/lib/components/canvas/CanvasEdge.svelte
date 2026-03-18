<script lang="ts">
	import type { CanvasNode } from '$lib/canvas/layout';

	let { fromNode, toNode, edgeId, edgeType, oncontextmenu }: {
		fromNode: CanvasNode;
		toNode: CanvasNode;
		edgeId: string;
		edgeType: string;
		oncontextmenu?: (e: MouseEvent) => void;
	} = $props();

	// Compute curved path with proper arrow endpoint
	let path = $derived.by(() => {
		const dx = toNode.x - fromNode.x;
		const dy = toNode.y - fromNode.y;
		const dist = Math.sqrt(dx * dx + dy * dy);
		if (dist === 0) return { d: '', mx: 0, my: 0, angle: 0 };

		const ux = dx / dist;
		const uy = dy / dist;

		// Offset from node centers
		const fromR = fromNode.type === 'owner' ? 44 : 36;
		const toR = toNode.type === 'owner' ? 44 : 36;

		const x1 = fromNode.x + ux * fromR;
		const y1 = fromNode.y + uy * fromR;
		const x2 = toNode.x - ux * toR;
		const y2 = toNode.y - uy * toR;

		// Midpoint for the arrow tip
		const angle = Math.atan2(y2 - y1, x2 - x1) * 180 / Math.PI;

		return { d: `M ${x1} ${y1} L ${x2} ${y2}`, x2, y2, angle };
	});
</script>

<!-- Wider invisible hit area -->
<path
	d={path.d}
	stroke="transparent"
	stroke-width="14"
	fill="none"
	class="cursor-pointer"
	oncontextmenu={(e) => { e.preventDefault(); oncontextmenu?.(e); }}
/>
<!-- Visible solid line -->
<path
	d={path.d}
	stroke="currentColor"
	stroke-width="1.5"
	fill="none"
	opacity="0.2"
	class="pointer-events-none"
	data-edge-id={edgeId}
	data-edge-type={edgeType}
/>
<!-- Arrowhead triangle -->
{#if path.x2 !== undefined}
	<polygon
		points="-6,-4 0,0 -6,4"
		fill="currentColor"
		opacity="0.25"
		transform="translate({path.x2},{path.y2}) rotate({path.angle})"
		class="pointer-events-none"
	/>
{/if}
