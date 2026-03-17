<script lang="ts">
	import { store } from '$lib/stores/app.svelte';
	import { api } from '$lib/api';
	import { onMount } from 'svelte';

	let showCreate = $state(false);
	let newName = $state('');
	let newPrompt = $state('');
	let newSchedule = $state('');

	onMount(() => {
		store.loadCron();
	});

	async function createJob() {
		if (!newPrompt.trim() || !newSchedule.trim()) return;
		await api.createCron({
			name: newName || 'Untitled Job',
			prompt: newPrompt,
			schedule: newSchedule
		});
		newName = '';
		newPrompt = '';
		newSchedule = '';
		showCreate = false;
		store.loadCron();
	}

	async function toggleJob(id: string, status: string) {
		await api.updateCron(id, {
			status: status === 'active' ? 'paused' : 'active'
		});
		store.loadCron();
	}

	async function deleteJob(id: string) {
		await api.deleteCron(id);
		store.loadCron();
	}
</script>

<div class="flex h-full flex-col">
	<header class="flex h-14 shrink-0 items-center justify-between border-b border-border px-6">
		<h2 class="font-semibold">Scheduled Jobs</h2>
		<button
			onclick={() => (showCreate = !showCreate)}
			class="rounded-lg bg-primary px-3 py-1.5 text-sm text-white hover:bg-primary-hover"
		>
			{showCreate ? 'Cancel' : '+ New Job'}
		</button>
	</header>

	<div class="flex-1 overflow-y-auto">
		<!-- Create form -->
		{#if showCreate}
			<div class="border-b border-border p-4">
				<div class="space-y-3">
					<input
						type="text"
						bind:value={newName}
						placeholder="Job name"
						class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					/>
					<textarea
						bind:value={newPrompt}
						placeholder="What should the agent do?"
						rows="3"
						class="w-full resize-none rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					></textarea>
					<input
						type="text"
						bind:value={newSchedule}
						placeholder="Schedule (e.g. '30m', '0 9 * * *', 'every day at 9am')"
						class="w-full rounded-lg border border-border bg-surface px-4 py-2 text-sm text-white placeholder-slate-500 focus:border-primary focus:outline-none"
					/>
					<button
						onclick={createJob}
						class="rounded-lg bg-primary px-4 py-2 text-sm text-white hover:bg-primary-hover"
					>
						Create Job
					</button>
				</div>
			</div>
		{/if}

		<!-- Job list -->
		{#if store.cronJobs.length === 0}
			<div class="flex h-full flex-col items-center justify-center text-slate-400">
				<svg class="mb-3 h-12 w-12 text-slate-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1">
					<path stroke-linecap="round" stroke-linejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
				</svg>
				<p class="text-sm font-medium">No scheduled jobs</p>
				<p class="text-xs text-slate-500 mt-1">Create cron jobs to automate recurring tasks</p>
			</div>
		{:else}
			<div class="divide-y divide-border">
				{#each store.cronJobs as job}
					<div class="p-4 hover:bg-surface-hover transition-colors">
						<div class="flex items-center justify-between mb-2">
							<div class="flex items-center gap-2">
								<span
									class="h-2 w-2 rounded-full"
									class:bg-green-500={job.status === 'active'}
									class:bg-yellow-500={job.status === 'paused'}
								></span>
								<span class="font-medium text-sm">{job.name}</span>
							</div>
							<div class="flex items-center gap-2">
								<button
									onclick={() => toggleJob(job.id, job.status)}
									class="rounded bg-surface px-2.5 py-1 text-xs hover:bg-surface-active"
									class:text-yellow-400={job.status === 'active'}
									class:text-green-400={job.status === 'paused'}
								>
									{job.status === 'active' ? 'Pause' : 'Resume'}
								</button>
								<button
									onclick={() => deleteJob(job.id)}
									class="rounded bg-surface px-2.5 py-1 text-xs text-red-400 hover:bg-surface-active"
								>
									Delete
								</button>
							</div>
						</div>
						<p class="text-sm text-slate-300 mb-1">{job.prompt}</p>
						<div class="flex items-center gap-4 text-xs text-slate-500">
							<span>Schedule: {job.schedule}</span>
							{#if job.last_run}
								<span>Last run: {new Date(job.last_run).toLocaleString()}</span>
							{/if}
						</div>
						{#if job.last_output}
							<div class="mt-2 rounded bg-slate-800 p-2 text-xs text-slate-400">
								{job.last_output}
							</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
	</div>
</div>
