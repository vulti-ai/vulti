<script lang="ts">
	import { BaseEdge, getBezierPath } from '@xyflow/svelte';

	let {
		id,
		sourceX,
		sourceY,
		targetX,
		targetY,
		sourcePosition,
		targetPosition,
		markerEnd,
		style,
		data,
	}: {
		id: string;
		sourceX: number;
		sourceY: number;
		targetX: number;
		targetY: number;
		sourcePosition: any;
		targetPosition: any;
		markerEnd?: string;
		style?: string;
		data?: { deletable?: boolean; ondelete?: (id: string) => void };
	} = $props();

	let edgePath = $derived.by(() => {
		const [path, labelX, labelY] = getBezierPath({
			sourceX, sourceY, targetX, targetY, sourcePosition, targetPosition,
		});
		return { path, labelX, labelY };
	});
</script>

<BaseEdge path={edgePath.path} {markerEnd} {style} />

{#if data?.deletable}
	<!-- Invisible fat hit area + delete button, all in SVG so hover is stable -->
	<path
		d={edgePath.path}
		fill="none"
		stroke="transparent"
		stroke-width="24"
		class="edge-hover-zone"
	/>
	<foreignObject
		x={edgePath.labelX - 12}
		y={edgePath.labelY - 12}
		width="24"
		height="24"
		class="edge-delete-fo"
	>
		<!-- svelte-ignore a11y_click_events_have_key_events -->
		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			xmlns="http://www.w3.org/1999/xhtml"
			class="delete-btn"
			onclick={(e: MouseEvent) => { e.stopPropagation(); data?.ondelete?.(id); }}
		>
			<svg width="8" height="8" viewBox="0 0 12 12" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
				<path d="M2 2l8 8M10 2l-8 8" />
			</svg>
		</div>
	</foreignObject>
{/if}

<style>
	.edge-delete-fo {
		overflow: visible;
		opacity: 0;
		transition: opacity 120ms ease;
		pointer-events: none;
	}

	/* Show delete button when hovering the fat hit area OR the button itself */
	.edge-hover-zone:hover ~ .edge-delete-fo,
	.edge-delete-fo:hover {
		opacity: 1;
		pointer-events: all;
	}

	.delete-btn {
		width: 24px;
		height: 24px;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		cursor: pointer;
		transition: all 100ms ease;
	}

	:global(html.light) .delete-btn {
		background: #EDE7DB;
		color: #9A938D;
		box-shadow: 0 1px 5px rgba(0, 0, 0, 0.1);
	}
	:global(html.light) .delete-btn:hover {
		background: #E8607A;
		color: #fff;
		box-shadow: 0 2px 8px rgba(232, 96, 122, 0.35);
	}

	:global(html.dark) .delete-btn {
		background: #302D2A;
		color: #6B6460;
		box-shadow: 0 1px 5px rgba(0, 0, 0, 0.25);
	}
	:global(html.dark) .delete-btn:hover {
		background: #E8607A;
		color: #fff;
		box-shadow: 0 2px 8px rgba(232, 96, 122, 0.35);
	}
</style>
