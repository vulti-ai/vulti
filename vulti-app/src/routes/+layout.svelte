<script lang="ts">
	import '../app.css';
	import { onMount } from 'svelte';

	let { children } = $props();
	let noiseCanvas: HTMLCanvasElement;

	/** Paper grain noise overlay */
	function initNoiseOverlay(canvas: HTMLCanvasElement) {
		if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

		const w = canvas.width = window.innerWidth;
		const h = canvas.height = window.innerHeight;
		const ctx = canvas.getContext('2d');
		if (!ctx) return;

		const imageData = ctx.createImageData(w, h);
		const data = imageData.data;
		for (let i = 0; i < data.length; i += 4) {
			const v = Math.random() * 255;
			data[i] = 139;
			data[i + 1] = 128;
			data[i + 2] = 112;
			data[i + 3] = Math.random() < 0.15 ? (v * 0.4) : 0;
		}
		ctx.putImageData(imageData, 0, 0);

		const handleResize = () => {
			canvas.width = window.innerWidth;
			canvas.height = window.innerHeight;
			const ctx2 = canvas.getContext('2d');
			if (!ctx2) return;
			const id = ctx2.createImageData(canvas.width, canvas.height);
			const d = id.data;
			for (let i = 0; i < d.length; i += 4) {
				const v = Math.random() * 255;
				d[i] = 139; d[i+1] = 128; d[i+2] = 112;
				d[i+3] = Math.random() < 0.15 ? (v * 0.4) : 0;
			}
			ctx2.putImageData(id, 0, 0);
		};
		window.addEventListener('resize', handleResize);
	}

	onMount(() => {
		const savedTheme = localStorage.getItem('vulti-theme') || 'light';
		document.documentElement.classList.toggle('dark', savedTheme === 'dark');
		document.documentElement.classList.toggle('light', savedTheme === 'light');

		if (noiseCanvas) {
			initNoiseOverlay(noiseCanvas);
		}
	});
</script>

<canvas bind:this={noiseCanvas} id="noise-overlay"></canvas>
<div class="ambient-glow glow-1"></div>
<div class="ambient-glow glow-2"></div>

{@render children()}
