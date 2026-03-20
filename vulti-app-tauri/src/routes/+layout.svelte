<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';

	let { children } = $props();
	let noiseDiv: HTMLDivElement;

	/** Generate a small noise tile and set as repeating background — no resize handler needed */
	function initNoiseOverlay(el: HTMLDivElement) {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

		const size = 256;
		const canvas = document.createElement('canvas');
		canvas.width = size;
		canvas.height = size;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const imageData = ctx.createImageData(size, size);
		const data = imageData.data;
		for (let i = 0; i < data.length; i += 4) {
			const v = Math.random() * 255;
			data[i] = 139;
			data[i + 1] = 128;
			data[i + 2] = 112;
			data[i + 3] = Math.random() < 0.15 ? (v * 0.4) : 0;
		}
		ctx.putImageData(imageData, 0, 0);

		el.style.backgroundImage = `url(${canvas.toDataURL()})`;
		el.style.backgroundRepeat = 'repeat';
	}

	onMount(() => {
		const savedTheme = localStorage.getItem('vulti-theme') || 'light';
		document.documentElement.classList.toggle('dark', savedTheme === 'dark');
		document.documentElement.classList.toggle('light', savedTheme === 'light');

		if (noiseDiv) {
			initNoiseOverlay(noiseDiv);
		}
	});
</script>

<div bind:this={noiseDiv} id="noise-overlay"></div>
<div class="ambient-glow glow-1"></div>
<div class="ambient-glow glow-2"></div>

{@render children()}
