<script lang="ts">
	let { data }: { data: { src?: string; alt?: string; width?: number; height?: number } } = $props();
</script>

{#if data.src}
	<img
		src={data.src}
		alt={data.alt || ''}
		width={data.width}
		height={data.height}
		class="max-w-full rounded-lg"
	/>
{/if}
