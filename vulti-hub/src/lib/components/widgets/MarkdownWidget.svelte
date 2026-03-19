<script lang="ts">
	import { marked } from 'marked';
	let { data }: { data: { content?: string } } = $props();
	let html = $derived(marked.parse(data.content || '', { async: false }) as string);
</script>

<div class="prose prose-sm max-w-none text-ink prose-headings:text-ink prose-p:text-ink-dim prose-strong:text-ink prose-a:text-primary">
	{@html html}
</div>
