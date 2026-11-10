<script lang="ts">
	// Thẻ thuật ngữ trong Danh Lục: chữ Hán gốc → bản dịch cố định.
	import type { Snippet } from 'svelte';

	let {
		source,
		target,
		note,
		actions
	}: { source: string; target: string; note?: string | null; actions?: Snippet } = $props();
</script>

<article class="tablet">
	<div class="terms">
		<span class="source" lang="zh">{source}</span>
		<span class="arrow" aria-hidden="true">→</span>
		<strong class="target">{target}</strong>
	</div>
	{#if note}<p class="note">{note}</p>{/if}
	{#if actions}<div class="actions">{@render actions()}</div>{/if}
</article>

<style>
	.tablet {
		display: flex;
		flex-direction: column;
		gap: 8px;
		padding: 14px 16px;
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
		border-left: 4px solid var(--jade);
	}
	.terms {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 6px 10px;
	}
	.source {
		font-family: var(--font-cjk);
		font-size: 20px;
		font-weight: 500;
	}
	.arrow {
		color: var(--ink-muted);
	}
	.target {
		font-family: var(--font-title);
		font-size: 21px;
	}
	.note {
		margin: 0;
		font-size: 13px;
		color: var(--ink-muted);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
</style>
