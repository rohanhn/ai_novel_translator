<script lang="ts">
	// Màn xem trước import (spec web-reader "Import preview screen").
	import type { ImportLang, ImportPreview, Novel } from '../types.js';
	import { commitImport, isExpired, uploadErrorMessage } from './imports.js';

	let {
		preview = $bindable(),
		onsaved,
		onexpired,
		oncancel
	}: {
		preview: ImportPreview;
		onsaved: (n: Novel) => void;
		onexpired: (message: string) => void;
		oncancel: () => void;
	} = $props();

	let title = $state('');
	let lang = $state<ImportLang>(preview.detected_lang === 'vi' ? 'vi' : 'zh');
	let busy = $state(false);
	let error = $state('');

	const keepFront = $derived(preview.front_matter ? preview.front_matter.keep : null);

	async function save() {
		busy = true;
		error = '';
		try {
			const novel = await commitImport(preview.id, {
				title: title.trim() || preview.default_title,
				lang,
				boundaries: preview.boundaries,
				keep_front_matter: keepFront
			});
			onsaved(novel);
		} catch (err) {
			if (isExpired(err)) onexpired(uploadErrorMessage(err));
			else error = uploadErrorMessage(err);
		} finally {
			busy = false;
		}
	}
</script>

<div class="preview">
	<label class="field-row">
		Tên truyện
		<input class="field" bind:value={title} placeholder={preview.default_title} maxlength="200" />
	</label>

	<fieldset class="lang">
		<legend>Ngôn ngữ của file</legend>
		<label
			><input type="radio" name="lang" value="zh" bind:group={lang} /> Tiếng Trung · cần dịch</label
		>
		<label
			><input type="radio" name="lang" value="vi" bind:group={lang} /> Tiếng Việt · bản dịch có sẵn</label
		>
	</fieldset>

	<p class="count"><strong>{preview.chapters.length}</strong> chương</p>

	<ol class="chapters">
		{#each preview.chapters as ch (ch.start_line)}
			<li>
				<span class="num">{ch.number}</span>
				<span class="t">{ch.title}</span>
				<span class="chars">{ch.chars.toLocaleString('vi-VN')} ký tự</span>
			</li>
		{/each}
	</ol>

	{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

	<div class="actions">
		<button type="button" class="btn" onclick={oncancel}>Huỷ</button>
		<button type="button" class="btn btn-primary" disabled={busy} onclick={save}>
			{busy ? 'Đang lưu…' : 'Lưu vào thư viện'}
		</button>
	</div>
</div>

<style>
	.preview {
		display: flex;
		flex-direction: column;
		gap: 14px;
		min-width: 0;
	}
	.field-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.lang {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 16px;
		margin: 0;
		padding: 0;
		border: none;
		font-size: 14px;
	}
	.lang legend {
		margin-bottom: 4px;
		font-weight: 600;
	}
	.lang label {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-height: var(--touch);
	}
	.count {
		margin: 0;
	}
	.chapters {
		margin: 0;
		padding: 0;
		list-style: none;
		max-height: 50dvh;
		overflow-y: auto;
		border-top: 1px solid var(--line);
	}
	.chapters li {
		display: grid;
		grid-template-columns: 3em 1fr auto;
		gap: 8px;
		padding: 8px 0;
		border-bottom: 1px solid var(--line);
		font-size: 14px;
	}
	.num,
	.chars {
		color: var(--ink-muted);
	}
	.t {
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
	}
</style>
