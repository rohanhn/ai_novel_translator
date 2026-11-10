<script lang="ts">
	// Upload hai bước (design D5): chọn file → xem trước cách tách chương → xác nhận mới lưu.
	import Modal from '../components/Modal.svelte';
	import { formatBytes } from '../realm.js';
	import type { ImportPreview as Preview, Novel } from '../types.js';
	import ImportPreview from './ImportPreview.svelte';
	import { MAX_UPLOAD_BYTES, createImport, discardImport, uploadErrorMessage } from './imports.js';

	let { open = $bindable(false), onuploaded }: { open?: boolean; onuploaded: (n: Novel) => void } =
		$props();

	let file = $state<File | null>(null);
	let preview = $state<Preview | null>(null);
	let error = $state('');
	let busy = $state(false);

	const tooLarge = $derived(!!file && file.size > MAX_UPLOAD_BYTES);

	$effect(() => {
		if (!open) reset();
	});

	function reset() {
		// Đóng khi đang xem trước mà chưa lưu = huỷ: bỏ bản xem trước ở server.
		if (preview) discardImport(preview.id);
		file = null;
		preview = null;
		error = '';
		busy = false;
	}

	function pick(e: Event) {
		file = (e.currentTarget as HTMLInputElement).files?.[0] ?? null;
		error = '';
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		if (!file || tooLarge) return;
		busy = true;
		error = '';
		try {
			preview = await createImport(file);
		} catch (err) {
			error = uploadErrorMessage(err);
		} finally {
			busy = false;
		}
	}

	function saved(novel: Novel) {
		preview = null; // đã lưu: không discard
		open = false;
		onuploaded(novel);
	}

	function expired(message: string) {
		preview = null;
		error = message;
	}
</script>

<Modal
	bind:open
	title={preview ? 'Xem trước' : 'Thu nạp điển tịch'}
	subtitle={preview ? 'Kiểm tra cách tách chương trước khi lưu' : 'Upload truyện .txt'}
	size={preview ? 'wide' : 'default'}
>
	{#if preview}
		<ImportPreview bind:preview onsaved={saved} onexpired={expired} oncancel={() => (open = false)} />
	{:else}
		<form onsubmit={submit} class="form">
			<label class="drop" class:bad={tooLarge}>
				{#if file}
					<span class="name">{file.name}</span>
					<span class="meta">{formatBytes(file.size)} · bấm để chọn file khác</span>
				{:else}
					<span class="name">Chọn file .txt</span>
					<span class="meta">Bấm để chọn file từ máy</span>
				{/if}
				<input type="file" accept=".txt,text/plain" onchange={pick} />
			</label>

			{#if tooLarge && file}
				<p role="alert" class="notice notice-danger">
					<strong>File quá lớn.</strong> Giới hạn là 50 MB, file này {formatBytes(file.size)}. Chưa
					có truyện nào được tạo. Hãy tách file rồi upload lại.
				</p>
			{/if}

			<p class="help">
				Tối đa 50 MB, mã hoá UTF-8 hoặc GB18030. File có thể gộp nhiều chương: app tự tách theo
				tiêu đề (第X章, Chương N, Hồi N…) và nhận ra file tiếng Trung hay bản dịch tiếng Việt có
				sẵn. Bạn sẽ được xem trước và chỉnh trước khi lưu.
			</p>

			{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

			<div class="actions">
				<button type="button" class="btn" onclick={() => (open = false)}>Huỷ</button>
				<button type="submit" class="btn btn-primary" disabled={!file || tooLarge || busy}>
					{busy ? 'Đang phân tích…' : 'Xem trước'}
				</button>
			</div>
		</form>
	{/if}
</Modal>

<style>
	.form {
		display: flex;
		flex-direction: column;
		gap: 16px;
	}
	.drop {
		position: relative;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		padding: 24px 16px;
		border: 2px dashed var(--bronze);
		background: var(--field);
		text-align: center;
		cursor: pointer;
	}
	.drop.bad {
		border-color: var(--cinnabar);
	}
	.drop:focus-within {
		outline: 2px solid var(--cinnabar);
		outline-offset: 2px;
	}
	.drop input {
		position: absolute;
		inset: 0;
		opacity: 0;
		cursor: pointer;
	}
	.name {
		font-size: 15px;
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	.meta,
	.help {
		font-size: 13px;
		font-weight: 400;
		color: var(--ink-muted);
	}
	.help {
		margin: 0;
		line-height: 1.55;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
	}
</style>
