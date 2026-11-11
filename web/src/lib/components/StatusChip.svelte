<script lang="ts">
	import { CHIP_LABELS, type ChipKind } from './status.js';

	let { kind, label }: { kind: ChipKind; label?: string } = $props();
	const tone: Record<ChipKind, string> = {
		pending: 'muted',
		translating: 'info',
		prefetching: 'info',
		translated: 'ok',
		edited: 'edited',
		failed: 'danger',
		glossary_outdated: 'warn',
		fallback: 'warn',
		possible_omission: 'warn',
		untranslated_han: 'warn'
	};
</script>

<span class="chip {tone[kind]}">{label ?? CHIP_LABELS[kind]}</span>

<style>
	.chip {
		display: inline-flex;
		align-items: center;
		padding: 3px 9px;
		border: 1px solid currentColor;
		font-size: 12px;
		font-weight: 600;
		line-height: 1.4;
		white-space: nowrap;
	}
	.muted {
		color: var(--ink-muted);
		border-color: var(--line-strong);
	}
	.info {
		color: var(--info-fg);
		background: var(--info-bg);
	}
	.ok {
		color: var(--ok-fg);
		background: var(--ok-bg);
	}
	.edited {
		color: var(--edited-fg);
		background: var(--edited-bg);
	}
	.warn {
		color: var(--warn-fg);
		background: var(--warn-bg);
	}
	.danger {
		color: var(--danger-fg);
		background: var(--danger-bg);
	}
</style>
