<script lang="ts">
	// "Pháp khí · chuỗi model": tình trạng lượt dùng hôm nay, bằng lời thường.
	import { onMount } from 'svelte';
	import { get } from '../api.js';

	type Step = { step: number; provider: string; exhausted: boolean; reset_at: string | null };
	let steps = $state<Step[] | null>(null);

	onMount(async () => {
		try {
			steps = (await get<{ steps: Step[] }>('/api/settings/quota')).steps;
		} catch {
			steps = null;
		}
	});

	const provider = $derived(
		steps?.[0] ? steps[0].provider.charAt(0).toUpperCase() + steps[0].provider.slice(1) : ''
	);
	const allOut = $derived(!!steps?.length && steps.every((s) => s.exhausted));
</script>

{#if steps}
	<a class="pill" class:out={allOut} href="/settings">
		<svg aria-hidden="true" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
			><path d="M12 2 4 8l8 14 8-14z" /></svg
		>
		<span><span class="xianxia">Pháp khí ·</span> {provider}: {allOut ? 'hết lượt hôm nay' : 'còn lượt hôm nay'}</span>
	</a>
{/if}

<style>
	.pill {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-height: var(--touch);
		padding: 0 14px;
		border: 1px solid var(--line-strong);
		border-radius: 999px;
		background: var(--paper-raised);
		font-size: 13px;
		color: var(--ink-soft);
		text-decoration: none;
	}
	.pill svg {
		color: var(--jade);
	}
	.out {
		border-color: var(--danger-line);
		background: var(--danger-bg);
		color: var(--danger-fg);
	}
	.out svg {
		color: var(--danger-fg);
	}
	@media (max-width: 480px) {
		.xianxia {
			display: none;
		}
	}
</style>
