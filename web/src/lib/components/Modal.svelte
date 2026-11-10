<script lang="ts">
	// Hộp thoại dùng <dialog> gốc: khóa focus, Esc để đóng, nền mờ.
	import type { Snippet } from 'svelte';

	let {
		open = $bindable(false),
		title,
		subtitle,
		role = 'dialog',
		tone = 'default',
		size = 'default',
		children
	}: {
		open?: boolean;
		title: string;
		subtitle?: string;
		role?: 'dialog' | 'alertdialog';
		tone?: 'default' | 'danger';
		/** `wide`: khung rộng trên desktop, toàn màn hình trên điện thoại. */
		size?: 'default' | 'wide';
		children: Snippet;
	} = $props();

	let el: HTMLDialogElement | undefined = $state();
	const id = `dlg-${Math.random().toString(36).slice(2, 8)}`;

	$effect(() => {
		if (!el) return;
		if (open && !el.open) el.showModal();
		if (!open && el.open) el.close();
	});
</script>

<dialog
	bind:this={el}
	class="{tone} {size}"
	{role}
	aria-labelledby="{id}-h"
	onclose={() => (open = false)}
	onclick={(e) => e.target === el && (open = false)}
>
	<div class="body">
		<header>
			<h2 id="{id}-h">
				{title}
				{#if subtitle}<span class="sub">{subtitle}</span>{/if}
			</h2>
			<button type="button" class="close" aria-label="Đóng" onclick={() => (open = false)}>×</button>
		</header>
		{@render children()}
	</div>
</dialog>

<style>
	dialog {
		width: min(560px, calc(100vw - 2 * var(--gutter)));
		max-height: calc(100dvh - 32px);
		margin: max(48px, 8vh) auto auto;
		padding: 0;
		border: 1px solid var(--line-strong);
		background: var(--paper-raised);
		color: var(--ink);
		box-shadow:
			inset 0 0 0 6px var(--paper-raised),
			inset 0 0 0 7px var(--line),
			0 24px 60px var(--shadow);
	}
	dialog.danger {
		border-color: var(--cinnabar);
		box-shadow:
			inset 0 0 0 6px var(--paper-raised),
			inset 0 0 0 7px var(--danger-line),
			0 24px 60px var(--shadow);
	}
	/* Khổ rộng: cao cố định vừa màn hình; nội dung tự cuộn bên trong (component con đặt
	   flex: 1 + min-height: 0), nút thao tác ở cuối luôn nằm trong khung nhìn. */
	dialog.wide {
		width: min(900px, calc(100vw - 2 * var(--gutter)));
		height: calc(100dvh - 48px);
		max-height: calc(100dvh - 48px);
		margin: 24px auto;
		overflow: hidden;
	}
	dialog.wide .body {
		box-sizing: border-box;
		height: 100%;
		min-height: 0;
	}
	@media (max-width: 640px) {
		dialog.wide {
			width: 100vw;
			max-width: 100vw;
			height: 100dvh;
			max-height: 100dvh;
			margin: 0;
		}
	}
	dialog::backdrop {
		background: var(--scrim);
	}
	.body {
		display: flex;
		flex-direction: column;
		gap: 16px;
		padding: 26px 28px;
	}
	header {
		display: flex;
		align-items: flex-start;
		gap: 12px;
	}
	h2 {
		flex: 1;
		font-size: 28px;
	}
	.sub {
		display: block;
		margin-top: 4px;
		font-family: var(--font-ui);
		font-size: 13px;
		font-weight: 500;
		color: var(--ink-muted);
	}
	.close {
		width: var(--touch);
		height: var(--touch);
		margin: -8px -10px 0 0;
		border: none;
		background: transparent;
		color: var(--ink);
		font-size: 24px;
		cursor: pointer;
	}
	@media (max-width: 480px) {
		.body {
			padding: 22px 18px;
		}
		h2 {
			font-size: 24px;
		}
	}
</style>
