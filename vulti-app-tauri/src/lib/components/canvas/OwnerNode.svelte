<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';

	let { data, selected }: {
		id: string;
		data: { label: string; color: string };
		selected: boolean;
		isConnectable: boolean;
	} = $props();
</script>

<div
	class="owner-node"
	style="border-color: {data.color}; {selected ? `box-shadow: 0 0 0 2px ${data.color}40;` : ''}"
>
	<div class="name">{data.label}</div>
	<div class="role" style="color: {data.color}">Human</div>

	<Handle type="source" position={Position.Bottom} />
	<Handle type="source" position={Position.Left} id="left-out" />
	<Handle type="source" position={Position.Right} id="right-out" />
</div>

<style>
	.owner-node {
		width: 80px;
		height: 80px;
		border-radius: 50%;
		border: 1.5px solid;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		font-family: 'Inter', sans-serif;
	}

	:global(html.light) .owner-node {
		background: rgba(245, 240, 232, 0.85);
	}
	:global(html.dark) .owner-node {
		background: rgba(38, 36, 34, 0.85);
	}

	.name {
		font-size: 14px;
		font-weight: 600;
		line-height: 1.2;
	}

	:global(html.light) .name { color: #1A1A1A; }
	:global(html.dark) .name { color: #E0DBD3; }

	.role {
		font-size: 10px;
		font-weight: 400;
		margin-top: 1px;
	}
</style>
