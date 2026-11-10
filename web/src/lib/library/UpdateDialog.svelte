<script lang="ts">
	// Cập nhật chương từ TXT (spec chapter-update, design D6): chọn file → xem trước cách tách
	// (dùng lại ImportPreview, ẩn tên/ngôn ngữ) → chọn chế độ và xem thay đổi → áp.
	import Modal from '../components/Modal.svelte';
	import { formatBytes } from '../realm.js';
	import type { ImportPreview as Preview, Novel, UpdateResult } from '../types.js';
	import ImportPreview from './ImportPreview.svelte';
	import { MAX_UPLOAD_BYTES, createImport, discardImport, uploadErrorMessage } from './imports.js';

	let {
		open = $bindable(false),
		novel,
		onupdated
	}: { open?: boolean; novel: Novel; onupdated: (r: UpdateResult) => void } = $props();

	type Step = 'file' | 'split' | 'changes';
	let step = $state<Step>('file');
	let file = $state<File | null>(null);
	let preview = $state<Preview | null>(null);
	let error = $state('');
	let busy = $state(false);

	const tooLarge = $derived(!!file && file.size > MAX_UPLOAD_BYTES);

	$effect(() => {
		if (!open) reset();
	});

	function reset() {
		// Đóng khi chưa áp = huỷ: bỏ bản xem trước ở server.
		if (preview) discardImport(preview.id);
		step = 'file';
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
			preview = await createImport(file, novel.id);
			step = 'split';
		} catch (err) {
			error = uploadErrorMessage(err);
		} finally {
			busy = false;
		}
	}

	function finished(result: UpdateResult) {
		preview = null; // đã áp: draft đã bị xoá ở server
		open = false;
		onupdated(result);
	}

	function expired(message: string) {
		preview = null;
		step = 'file';
		error = message;
	}

	const subtitles: Record<Step, string> = {
		file: 'Upload file .txt có chương mới hoặc cả bộ',
		split: 'Kiểm tra cách tách chương của file',
		changes: 'Chọn cách cập nhật và xem thay đổi'
	};
</script>

<Modal
	bind:open
	title="Cập nhật từ txt"
	subtitle={`${novel.title} · ${subtitles[step]}`}
	size={step === 'file' ? 'default' : 'wide'}
>
	{#if step === 'split' && preview}
		<ImportPreview
			bind:preview
			onnext={() => (step = 'changes')}
			onexpired={expired}
			oncancel={() => (open = false)}
		/>
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
					<strong>File quá lớn.</strong> Giới hạn là 50 MB, file này {formatBytes(file.size)}. Truyện
					chưa bị thay đổi.
				</p>
			{/if}

			<p class="help">
				File có thể là bản tải lại cả bộ hoặc chỉ gồm các chương mới. Bạn sẽ xem cách tách chương,
				rồi chọn thêm chương mới hay tải lại cả bộ và xem trước thay đổi. Chưa có gì được lưu cho tới
				khi bạn xác nhận.
			</p>

			{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

			<div class="actions">
				<button type="button" class="btn" onclick={() => (open = false)}>Huỷ</button>
				<button type="submit" class="btn btn-primary" disabled={!file || tooLarge || busy}>
					{busy ? 'Đang phân tích…' : 'Xem cách tách chương'}
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
