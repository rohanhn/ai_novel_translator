<script lang="ts">
	// Khung viền kép như cuộn thư.
	import type { Snippet } from 'svelte';

	let {
		children,
		tag = 'section',
		tone = 'default',
		padding = '28px 28px',
		...rest
	}: {
		children: Snippet;
		tag?: string;
		tone?: 'default' | 'danger';
		padding?: string;
		[key: string]: unknown;
	} = $props();
</script>

<svelte:element this={tag} class="scroll-frame {tone}" style:--pad={padding} {...rest}>
	{@render children()}
</svelte:element>

<style>
	.scroll-frame {
		position: relative;
		padding: var(--pad);
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
		box-shadow:
			inset 0 0 0 6px var(--paper-raised),
			inset 0 0 0 7px var(--line);
		overflow: hidden;
	}
	.danger {
		border-color: var(--cinnabar);
		box-shadow:
			inset 0 0 0 6px var(--paper-raised),
			inset 0 0 0 7px var(--danger-line);
	}
	@media (max-width: 480px) {
		.scroll-frame {
			padding: 22px 18px;
		}
	}
</style>
