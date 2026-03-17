<script lang="ts">
	/**
	 * Vulti logo — ASCII block art with animated rainbow gradient.
	 * Matches the landing page hero-ascii style.
	 *
	 * mode="icon"     → Single "H" block character (for avatars, sidebar collapsed)
	 * mode="wordmark"  → Full "HECTOR" ASCII block text
	 */
	let { mode = 'icon', size = 32, class: className = '' }: {
		mode?: 'icon' | 'wordmark';
		size?: number;
		class?: string;
	} = $props();
</script>

{#if mode === 'icon'}
	<!-- Single H block character -->
	<pre
		class="vulti-logo {className}"
		aria-label="Vulti"
		style="font-size: {size * 0.14}px; line-height: 1.1; width: {size}px; height: {size}px; display: flex; align-items: center; justify-content: center;"
	>██╗  ██╗
██║  ██║
███████║
██╔══██║
██║  ██║
╚═╝  ╚═╝</pre>
{:else}
	<!-- Full HECTOR wordmark -->
	<pre
		class="vulti-logo {className}"
		aria-label="Vulti"
		style="font-size: {size * 0.22}px; line-height: 1.15;"
	>██╗  ██╗███████╗ ██████╗████████╗ ██████╗ ██████╗
██║  ██║██╔════╝██╔════╝╚══██╔══╝██╔═══██╗██╔══██╗
███████║█████╗  ██║        ██║   ██║   ██║██████╔╝
██╔══██║██╔══╝  ██║        ██║   ██║   ██║██╔══██╗
██║  ██║███████╗╚██████╗   ██║   ╚██████╔╝██║  ██║
╚═╝  ╚═╝╚══════╝ ╚═════╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝</pre>
{/if}

<style>
	.vulti-logo {
		margin: 0;
		padding: 0;
		font-family: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace;
		font-variant-ligatures: none;
		white-space: pre;
		background: linear-gradient(
			90deg,
			#E8607A,
			#F28B6D,
			#F0A84A,
			#8BC867,
			#4AC6B7,
			#5AADE0,
			#6B8BEB,
			#9D7AEA,
			#D96BA8
		);
		background-size: 200% 100%;
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		animation: rainbow-shift 8s linear infinite;
		user-select: none;
	}

	@keyframes rainbow-shift {
		0%   { background-position: 0% 50%; }
		100% { background-position: 200% 50%; }
	}

	@media (prefers-reduced-motion: reduce) {
		.vulti-logo {
			animation: none;
		}
	}
</style>
