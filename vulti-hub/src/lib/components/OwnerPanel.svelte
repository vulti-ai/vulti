<script lang="ts">
	import { store } from '$lib/stores/app.svelte';

	let name = $state(store.owner.name);
	let saving = $state(false);

	async function save() {
		saving = true;
		try {
			await store.updateOwner(name);
		} finally {
			saving = false;
		}
	}
</script>

<div class="space-y-6 p-4">
	<h2 class="text-lg font-semibold text-ink">Profile</h2>

	<div class="space-y-3">
		<label class="block text-sm font-medium text-ink/60">Name</label>
		<input
			type="text"
			bind:value={name}
			class="w-full rounded-lg border border-ink/10 bg-paper px-3 py-2 text-sm text-ink focus:border-primary focus:outline-none"
			placeholder="Your name"
			onkeydown={(e) => e.key === 'Enter' && save()}
		/>
	</div>

	<button
		class="rounded-lg bg-primary px-4 py-2 text-sm font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
		disabled={saving || name === store.owner.name}
		onclick={save}
	>
		{saving ? 'Saving...' : 'Save'}
	</button>
</div>
