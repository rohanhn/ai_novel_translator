<script lang="ts">
	import { ApiError, api } from '../api.js';
	import Modal from '../components/Modal.svelte';
	import { formatBytes } from '../realm.js';
	import type { Novel } from '../types.js';

	const MAX_BYTES = 50 * 1024 * 1024;

	let { open = $bindable(false), onuploaded }: { open?: boolean; onuploaded: (n: Novel) => void } =
		$props();

	let file = $state<File | null>(null);
	let title = $state('');
	let error = $state('');
	let busy = $state(false);
	let input: HTMLInputElement | undefined = $state();

	const tooLarge = $derived(!!file && file.size > MAX_BYTES);
	const placeholder = $derived(file ? file.name.replace(/\.txt$/i, '') : 'Tên file');

	$effect(() => {
		if (!open) reset();
	});

	function reset() {
		file = null;
		title = '';
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
		const form = new FormData();
		form.append('file', file);
		if (title.trim()) form.append('title', title.trim());
		try {
			const novel = await api<Novel>('/api/novels', { method: 'POST', body: form });
			open = false;
			onuploaded(novel);
		} catch (err) {
			if (err instanceof ApiError && err.status === 413) {
				error = 'File quá lớn. Giới hạn là 50 MB. Chưa có truyện nào được tạo.';
			} else {
				error = err instanceof ApiError ? err.message : 'Không upload được. Thử lại sau.';
			}
		} finally {
			busy = false;
		}
	}
</script>

<Modal bind:open title="Thu nạp điển tịch" subtitle="Upload truyện .txt">
	<form onsubmit={submit} class="form">
		<label class="drop" class:bad={tooLarge}>
			{#if file}
				<span class="name">{file.name}</span>
				<span class="meta">{formatBytes(file.size)} · bấm để chọn file khác</span>
			{:else}
				<span class="name">Chọn file .txt</span>
				<span class="meta">Bấm để chọn file từ máy</span>
			{/if}
			<input bind:this={input} type="file" accept=".txt,text/plain" onchange={pick} />
		</label>

		{#if tooLarge && file}
			<p role="alert" class="notice notice-danger">
				<strong>File quá lớn.</strong> Giới hạn là 50 MB, file này {formatBytes(file.size)}. Chưa có
				truyện nào được tạo. Hãy tách file rồi upload lại.
			</p>
		{/if}

		<label class="title">
			Tên truyện
			<span class="hint">Không bắt buộc. Để trống sẽ dùng tên file.</span>
			<input class="field" bind:value={title} {placeholder} maxlength="200" />
		</label>

		<p class="help">
			Tối đa 50 MB. Tự nhận diện mã hoá UTF-8 hoặc GB18030 và tách chương theo 第X章, 第X回, 第X节,
			第X卷.
		</p>

		{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

		<div class="actions">
			<button type="button" class="btn" onclick={() => (open = false)}>Huỷ</button>
			<button type="submit" class="btn btn-primary" disabled={!file || tooLarge || busy}>
				{busy ? 'Đang upload…' : 'Upload'}
			</button>
		</div>
	</form>
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
	.hint,
	.help {
		font-size: 13px;
		font-weight: 400;
		color: var(--ink-muted);
	}
	.title {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
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
