<script lang="ts">
	// Sửa thông tin truyện (spec web-reader "Edit novel details screen", "Cover selection in the
	// edit form", "Edit form layout"; design D6). Không lưu gì cho tới khi bấm Lưu.
	import Cover from '../components/Cover.svelte';
	import Modal from '../components/Modal.svelte';
	import type { Novel } from '../types.js';
	import {
		AUTHOR_MAX,
		DESCRIPTION_MAX,
		TITLE_MAX,
		type DetailsField,
		type DetailsPatch,
		coverFileProblem,
		errorField,
		errorMessage,
		fetchCoverFromUrl,
		removeCover,
		updateDetails,
		uploadCover
	} from './details.js';

	let {
		open = $bindable(false),
		novel,
		onsaved
	}: { open?: boolean; novel: Novel; onsaved: (n: Novel) => void } = $props();

	type CoverChoice =
		| { kind: 'keep' }
		| { kind: 'new'; blob: Blob; name: string; url: string }
		| { kind: 'remove' };

	let title = $state('');
	let author = $state('');
	let description = $state('');
	let link = $state('');
	let cover = $state<CoverChoice>({ kind: 'keep' });
	let errors = $state<Partial<Record<DetailsField, string>>>({});
	let notice = $state('');
	let busy = $state(false);
	let fetching = $state(false);
	let fileInput: HTMLInputElement | undefined = $state();
	let wasOpen = false;

	const formId = $derived(`edit-novel-${novel.id}`);
	const previewSrc = $derived(
		cover.kind === 'new' ? cover.url : cover.kind === 'remove' ? null : novel.cover_url
	);
	const canRemove = $derived(cover.kind === 'new' || (cover.kind === 'keep' && !!novel.cover_url));

	$effect(() => {
		if (open && !wasOpen) init();
		if (!open && wasOpen) release();
		wasOpen = open;
	});

	function init() {
		title = novel.title;
		author = novel.author ?? '';
		description = novel.description ?? '';
		link = '';
		cover = { kind: 'keep' };
		errors = {};
		notice = '';
		busy = false;
		fetching = false;
	}

	function release() {
		if (cover.kind === 'new') URL.revokeObjectURL(cover.url);
		cover = { kind: 'keep' };
	}

	function choose(blob: Blob, name: string) {
		release();
		cover = { kind: 'new', blob, name, url: URL.createObjectURL(blob) };
		errors = { ...errors, cover: undefined, cover_url: undefined };
	}

	function pick(e: Event) {
		const input = e.currentTarget as HTMLInputElement;
		const file = input.files?.[0];
		input.value = '';
		if (!file) return;
		const problem = coverFileProblem(file);
		if (problem) {
			errors = { ...errors, cover: problem };
			return;
		}
		choose(file, file.name);
	}

	function removeChosen() {
		release();
		cover = { kind: 'remove' };
		errors = { ...errors, cover: undefined };
	}

	async function fetchLink() {
		const url = link.trim();
		if (!url || fetching) return;
		fetching = true;
		errors = { ...errors, cover_url: undefined };
		try {
			choose(await fetchCoverFromUrl(url), 'bia-tu-link.webp');
		} catch (err) {
			errors = { ...errors, cover_url: errorMessage(err) };
		} finally {
			fetching = false;
		}
	}

	function linkKey(e: KeyboardEvent) {
		if (e.key === 'Enter') {
			e.preventDefault();
			fetchLink();
		}
	}

	function textPatch(): DetailsPatch {
		const p: DetailsPatch = {};
		if (title !== novel.title) p.title = title;
		if (author.trim() !== (novel.author ?? '')) p.author = author;
		if (description.trim() !== (novel.description ?? '')) p.description = description;
		return p;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		if (busy || fetching) return;
		busy = true;
		errors = {};
		notice = '';
		const patch = textPatch();
		let result: Novel = novel;
		try {
			if (Object.keys(patch).length) result = await updateDetails(novel.id, patch);
		} catch (err) {
			errors = { [errorField(err) ?? 'title']: errorMessage(err) };
			busy = false;
			return;
		}
		const textSaved = result !== novel;
		try {
			if (cover.kind === 'new') result = await uploadCover(novel.id, cover.blob, cover.name);
			else if (cover.kind === 'remove' && novel.cover_url) {
				await removeCover(novel.id);
				result = { ...result, cover_url: null };
			}
		} catch (err) {
			errors = { cover: errorMessage(err) };
			if (textSaved) {
				notice = `Đã lưu thông tin; ảnh bìa chưa lưu: ${errorMessage(err)}`;
				onsaved(result); // trang hiện tên/tác giả mới, hộp vẫn mở để chọn lại ảnh
			}
			busy = false;
			return;
		}
		busy = false;
		release();
		open = false;
		onsaved(result);
	}

	const invalid = (f: DetailsField) => (errors[f] ? 'true' : undefined);
	const describedBy = (f: DetailsField) => (errors[f] ? `${formId}-${f}-err` : undefined);
</script>

<Modal bind:open title="Sửa thông tin" subtitle="Tên, tác giả, giới thiệu và ảnh bìa">
	<form id={formId} class="form" onsubmit={save} novalidate aria-busy={busy}>
		<div class="cover-col">
			<div class="cover-box">
				<Cover id={novel.id} title={title.trim() || novel.title} height={210} src={previewSrc} />
			</div>
			<div class="cover-actions">
				<button type="button" class="btn" onclick={() => fileInput?.click()}>Chọn ảnh…</button>
				{#if canRemove}
					<button type="button" class="btn btn-ghost" onclick={removeChosen}>Gỡ ảnh</button>
				{/if}
			</div>
			<input
				bind:this={fileInput}
				class="sr-only"
				type="file"
				accept="image/jpeg,image/png,image/webp"
				aria-label="Chọn ảnh bìa từ máy"
				tabindex="-1"
				onchange={pick}
			/>
			<p class="hint">
				{#if cover.kind === 'new'}Ảnh mới, sẽ lưu khi bấm Lưu.
				{:else if cover.kind === 'remove'}Sẽ dùng bìa tự vẽ khi bấm Lưu.
				{:else}JPG, PNG hoặc WebP, tối đa 10 MB.{/if}
			</p>
			{#if errors.cover}
				<p class="err" role="alert" id="{formId}-cover-err">{errors.cover}</p>
			{/if}
		</div>

		<div class="fields">
			<div class="group">
				<label for="{formId}-link">Hoặc dán link ảnh</label>
				<div class="link">
					<input
						id="{formId}-link"
						class="field"
						type="url"
						inputmode="url"
						placeholder="https://…"
						bind:value={link}
						onkeydown={linkKey}
						aria-invalid={invalid('cover_url')}
						aria-describedby={describedBy('cover_url')}
					/>
					<button
						type="button"
						class="btn"
						onclick={fetchLink}
						disabled={!link.trim() || fetching}
					>
						{fetching ? 'Đang tải ảnh…' : 'Lấy ảnh'}
					</button>
				</div>
				{#if errors.cover_url}
					<p class="err" role="alert" id="{formId}-cover_url-err">{errors.cover_url}</p>
				{:else}
					<p class="hint">Máy chủ tải ảnh về và lưu bản sao; trang ảnh không thấy bạn.</p>
				{/if}
			</div>

			<div class="group">
				<label for="{formId}-title">Tên truyện</label>
				<input
					id="{formId}-title"
					class="field"
					bind:value={title}
					maxlength={TITLE_MAX}
					required
					aria-invalid={invalid('title')}
					aria-describedby={describedBy('title')}
				/>
				{#if errors.title}<p class="err" role="alert" id="{formId}-title-err">{errors.title}</p>{/if}
			</div>

			<div class="group">
				<label for="{formId}-author">Tác giả</label>
				<input
					id="{formId}-author"
					class="field"
					bind:value={author}
					maxlength={AUTHOR_MAX}
					aria-invalid={invalid('author')}
					aria-describedby={describedBy('author')}
				/>
				{#if errors.author}<p class="err" role="alert" id="{formId}-author-err">{errors.author}</p>{/if}
			</div>

			<div class="group">
				<label for="{formId}-description">
					Giới thiệu ngắn
					<span class="count" aria-live="polite">{description.length}/{DESCRIPTION_MAX}</span>
				</label>
				<textarea
					id="{formId}-description"
					class="field"
					rows="6"
					bind:value={description}
					maxlength={DESCRIPTION_MAX}
					aria-invalid={invalid('description')}
					aria-describedby={describedBy('description')}
				></textarea>
				{#if errors.description}
					<p class="err" role="alert" id="{formId}-description-err">{errors.description}</p>
				{/if}
			</div>

			{#if notice}<p class="notice notice-warn" role="status">{notice}</p>{/if}
		</div>
	</form>

	{#snippet footer()}
		<button type="button" class="btn" onclick={() => (open = false)}>Huỷ</button>
		<button type="submit" form={formId} class="btn btn-primary" disabled={busy || fetching}>
			{busy ? 'Đang lưu…' : 'Lưu'}
		</button>
	{/snippet}
</Modal>

<style>
	.form {
		display: grid;
		grid-template-columns: 150px minmax(0, 1fr);
		gap: 20px;
		align-items: start;
	}
	.cover-col {
		display: flex;
		flex-direction: column;
		gap: 10px;
		min-width: 0;
	}
	.cover-box {
		width: 150px;
	}
	.cover-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.cover-actions .btn {
		flex: 1 1 auto;
	}
	.fields {
		display: flex;
		flex-direction: column;
		gap: 16px;
		min-width: 0;
	}
	.group {
		display: flex;
		flex-direction: column;
		gap: 6px;
		min-width: 0;
	}
	label {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		font-size: 14px;
		font-weight: 600;
	}
	.count {
		font-weight: 400;
		font-size: 13px;
		color: var(--ink-muted);
	}
	.field {
		width: 100%;
		box-sizing: border-box;
	}
	textarea.field {
		resize: vertical;
		line-height: 1.55;
	}
	.link {
		display: flex;
		gap: 8px;
		min-width: 0;
	}
	.link .field {
		flex: 1;
		min-width: 0;
	}
	.link .btn {
		flex: none;
	}
	.hint,
	.err {
		margin: 0;
		font-size: 13px;
		line-height: 1.5;
	}
	.hint {
		color: var(--ink-muted);
	}
	.err {
		color: var(--danger-fg);
		font-weight: 600;
	}
	@media (max-width: 560px) {
		.form {
			grid-template-columns: minmax(0, 1fr);
		}
		.cover-col {
			display: grid;
			grid-template-columns: 110px minmax(0, 1fr);
			column-gap: 14px;
			row-gap: 8px;
			align-items: start;
		}
		.cover-box {
			width: 110px;
			grid-row: span 3;
		}
		.cover-actions {
			flex-direction: column;
		}
	}
</style>
