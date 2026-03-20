<script lang="ts">
	import { Handle, Position } from '@xyflow/svelte';

	let { data, selected }: {
		id: string;
		data: { label: string; sublabel: string; color: string; status?: string; avatarUri?: string };
		selected: boolean;
		isConnectable: boolean;
	} = $props();

	function statusColor(status?: string): string {
		if (!status) return '#9A938D';
		if (['connected', 'active', 'ready'].includes(status)) return '#8BC867';
		if (['disconnected', 'stopped', 'setting_up'].includes(status)) return '#F0A84A';
		return '#E8607A';
	}
</script>

<div
	class="agent-node"
	style="border-color: {data.color}; {selected ? `box-shadow: 0 0 0 2px ${data.color}40;` : ''}"
>
	<Handle type="target" position={Position.Top} />
	<Handle type="target" position={Position.Left} id="left-in" />

	<div class="status-dot" style="background: {statusColor(data.status)}"></div>

	{#if data.avatarUri}
		<img class="avatar" src={data.avatarUri} alt={data.label} />
	{/if}
	<div class="label">{data.label}</div>
	{#if data.sublabel}
		<div class="sublabel" style="color: {data.color}">{data.sublabel}</div>
	{/if}

	<Handle type="source" position={Position.Bottom} />
	<Handle type="source" position={Position.Right} id="right-out" />
</div>

<style>
	.agent-node {
		padding: 8px 20px;
		border-radius: 10px;
		border: 1px solid;
		min-width: 100px;
		text-align: center;
		font-family: 'Inter', sans-serif;
		position: relative;
	}

	:global(html.light) .agent-node {
		background: rgba(245, 240, 232, 0.85);
	}
	:global(html.dark) .agent-node {
		background: rgba(38, 36, 34, 0.85);
	}

	.avatar {
		width: 32px;
		height: 32px;
		border-radius: 6px;
		object-fit: cover;
		margin: 0 auto 4px;
	}

	.label {
		font-size: 13px;
		font-weight: 500;
		line-height: 1.3;
	}

	:global(html.light) .label { color: #1A1A1A; }
	:global(html.dark) .label { color: #E0DBD3; }

	.sublabel {
		font-size: 11px;
		font-weight: 400;
		margin-top: 1px;
	}

	.status-dot {
		position: absolute;
		top: 6px;
		right: 6px;
		width: 7px;
		height: 7px;
		border-radius: 50%;
	}
</style>
