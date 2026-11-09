<script lang="ts">
	// Biên tập tay bản dịch (spec translation-editing). Lưu → trạng thái "Đã biên tập".
	import { beforeNavigate } from '$app/navigation';
	import { untrack } from 'svelte';
	import { ApiError, put } from '../api.js';
	import type { Chapter } from '../types.js';

	let {
		novelId,
		chapter,
		onsaved,
		oncancel
	}: {
		novelId: number;
		chapter: Chapter;
		onsaved: (c: Chapter) => void;
		oncancel: () => void;
	} = $props();

	// Bản nháp lấy giá trị ban đầu một lần (không đồng bộ ngược với prop).
	const initial = untrack(() => ({
		title: chapter.translated_title ?? '',
		text: chapter.translated_text ?? ''
	}));
	let title = $state(initial.title);
	let text = $state(initial.text);
	let busy = $state(false);
	let saved = false;
	let error = $state('');

	const dirty = $derived(title !== initial.title || text !== initial.text);
	const empty = $derived(!text.trim());
	const sourceParas = $derived(chapter.source_text.split('\n').filter((p) => p.trim()));

	beforeNavigate((nav) => {
		if (dirty && !saved && !confirm('Bản sửa chưa được lưu. Rời trang và bỏ thay đổi?')) nav.cancel();
	});

	function onBeforeUnload(e: BeforeUnloadEvent) {
		if (dirty && !saved) e.preventDefault();
	}

	function cancel() {
		if (dirty && !confirm('Bỏ các thay đổi chưa lưu?')) return;
		oncancel();
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (empty) {
			error = 'Nội dung bản dịch không được để trống.';
			return;
		}
		busy = true;
		error = '';
		try {
			const c = await put<Chapter>(`/api/novels/${novelId}/chapters/${chapter.index}`, {
				translated_title: title.trim() || null,
				translated_text: text
			});
			saved = true;
			onsaved(c);
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Không lưu được. Thử lại sau.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:window onbeforeunload={onBeforeUnload} />

<div class="workspace">
	<section class="source" aria-label="Bản gốc">
		<span class="label">Bản gốc</span>
		<span class="cn" lang="zh">{chapter.title}</span>
		<div lang="zh">
			{#each sourceParas as p, i (i)}<p>{p}</p>{/each}
		</div>
	</section>

	<form class="editor" aria-label="Biên tập chương" onsubmit={save}>
		<label>
			Tiêu đề
			<input class="field" bind:value={title} maxlength="300" />
		</label>
		<label class="grow">
			Nội dung
			<span class="hint">Mỗi dòng là một đoạn.</span>
			<textarea class="field" bind:value={text} rows="16" aria-invalid={empty ? 'true' : undefined}></textarea>
		</label>
		{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}
		<div class="actions">
			<span class="state" role="status">{dirty ? 'Chưa lưu thay đổi' : 'Không có thay đổi'}</span>
			<button type="button" class="btn" onclick={cancel}>Huỷ</button>
			<button type="submit" class="btn btn-primary" disabled={!dirty || busy || empty}>
				{busy ? 'Đang lưu…' : 'Lưu bản sửa'}
			</button>
		</div>
	</form>
</div>

<style>
	.workspace {
		display: grid;
		grid-template-columns: minmax(0, 1fr);
		gap: 20px;
		font-family: var(--font-ui);
	}
	.source {
		display: none;
	}
	.label {
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.14em;
		text-transform: uppercase;
		color: var(--label);
	}
	.cn {
		display: block;
		margin: 6px 0 12px;
		font-family: var(--font-han);
		font-size: 22px;
	}
	.source p {
		margin: 0 0 0.8em;
		font-family: var(--font-cjk);
		font-size: 16px;
		line-height: 1.8;
	}
	.editor {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.hint {
		font-size: 12px;
		font-weight: 400;
		color: var(--ink-muted);
	}
	.field {
		font-weight: 400;
	}
	textarea {
		min-height: 50dvh;
		resize: vertical;
		font-family: var(--font-body);
		font-size: var(--reader-size);
		line-height: 1.7;
	}
	.actions {
		position: sticky;
		bottom: 0;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: flex-end;
		gap: 10px;
		padding: 10px 0;
		background: var(--paper);
	}
	.state {
		flex: 1 1 140px;
		font-size: 13px;
		color: var(--ink-muted);
	}
	@media (max-width: 480px) {
		.state {
			flex-basis: 100%;
		}
		.actions .btn {
			flex: 1;
		}
	}
	@media (min-width: 1024px) {
		.workspace {
			grid-template-columns: minmax(0, 1fr) minmax(0, 1.2fr);
			gap: 32px;
		}
		.source {
			display: block;
			position: sticky;
			top: 64px;
			max-height: calc(100dvh - 80px);
			overflow-y: auto;
			padding: 16px 20px;
			background: var(--paper-raised);
			border: 1px solid var(--line-strong);
		}
	}
</style>
