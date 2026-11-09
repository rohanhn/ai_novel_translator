<script lang="ts">
	import { ApiError, del } from '../api.js';
	import Modal from '../components/Modal.svelte';

	let {
		novel = $bindable(null),
		ondeleted
	}: { novel?: { id: number; title: string } | null; ondeleted: (id: number) => void } = $props();

	let open = $state(false);
	let busy = $state(false);
	let error = $state('');

	$effect(() => {
		open = novel !== null;
		error = '';
	});
	$effect(() => {
		if (!open) novel = null;
	});

	async function confirm() {
		if (!novel) return;
		busy = true;
		try {
			await del(`/api/novels/${novel.id}?confirm=true`);
			const id = novel.id;
			novel = null;
			ondeleted(id);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Không xoá được. Thử lại sau.';
		} finally {
			busy = false;
		}
	}
</script>

<Modal bind:open title={`Xoá "${novel?.title ?? ''}"?`} role="alertdialog" tone="danger">
	<p class="desc">
		Toàn bộ raw, bản dịch, bộ tên, tên chờ duyệt và tiến độ đọc của truyện này sẽ bị xoá. Không thể
		hoàn tác.
	</p>
	{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}
	<div class="actions">
		<button type="button" class="btn" onclick={() => (novel = null)}>Giữ lại</button>
		<button type="button" class="btn btn-primary" disabled={busy} onclick={confirm}>
			{busy ? 'Đang xoá…' : 'Xoá truyện'}
		</button>
	</div>
</Modal>

<style>
	.desc {
		margin: 0;
		font-size: 14px;
		line-height: 1.6;
		color: var(--ink-soft);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
	}
</style>
