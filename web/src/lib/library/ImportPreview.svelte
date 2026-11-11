<script lang="ts">
	// Màn xem trước import (spec web-reader "Import preview screen", "Adjust chapters in the
	// preview"). Mọi chỉnh sửa gửi tập ranh giới lên server; server tính lại chương + cảnh báo.
	import { SvelteMap } from 'svelte/reactivity';
	import type { ImportChapter, ImportLang, ImportPreview, Novel } from '../types.js';
	import {
		adjustImport,
		commitImport,
		importLines,
		isExpired,
		uploadErrorMessage
	} from './imports.js';

	const LINES_PAGE = 200;

	let {
		preview = $bindable(),
		onsaved,
		onnext,
		onexpired,
		oncancel
	}: {
		preview: ImportPreview;
		/** Import truyện mới: lưu vào thư viện. */
		onsaved?: (n: Novel) => void;
		/** Cập nhật chương (draft có `novel_id`): ẩn tên + ngôn ngữ, nút chính sang bước kế. */
		onnext?: () => void;
		onexpired: (message: string) => void;
		oncancel: () => void;
	} = $props();

	const updating = $derived(preview.novel_id != null);

	let title = $state('');
	// svelte-ignore state_referenced_locally
	let lang = $state<ImportLang>(preview.detected_lang === 'vi' ? 'vi' : 'zh');
	let onlyWarnings = $state(false);
	let busy = $state(false);
	let error = $state('');
	let status = $state('');
	// Dòng của chương đang mở rộng, theo start_line của chương.
	let expanded = $state<number | null>(null);
	const loaded = new SvelteMap<number, { start: number; lines: string[]; done: boolean }>();

	const keepFront = $derived(preview.front_matter ? preview.front_matter.keep : null);
	const boundarySet = $derived(new Set(preview.boundaries));
	const warned = $derived(preview.chapters.filter((c) => c.warnings.length > 0));
	const shown = $derived(onlyWarnings ? warned : preview.chapters);
	const totalWarnings = $derived(
		warned.reduce((n, c) => n + c.warnings.length, 0) +
			preview.warnings.filter((w) => w.code !== 'front_matter').length
	);

	function fail(err: unknown) {
		if (isExpired(err)) onexpired(uploadErrorMessage(err));
		else error = uploadErrorMessage(err);
	}

	async function apply(boundaries: number[], keep: boolean | null, done: string) {
		busy = true;
		error = '';
		try {
			preview = await adjustImport(preview.id, boundaries, keep);
			loaded.clear();
			expanded = null;
			status = done;
		} catch (err) {
			fail(err);
		} finally {
			busy = false;
		}
	}

	function merge(ch: ImportChapter) {
		apply(
			preview.boundaries.filter((b) => b !== ch.start_line),
			keepFront,
			`Đã gộp "${ch.title}" vào chương trước.`
		);
	}

	function splitAt(line: number, text: string) {
		apply(
			[...preview.boundaries, line].sort((a, b) => a - b),
			keepFront,
			`Đã tách chương mới tại "${text.trim().slice(0, 40)}".`
		);
	}

	function setKeepFront(keep: boolean) {
		apply(
			preview.boundaries,
			keep,
			keep ? 'Phần đầu file sẽ thành chương "Mở đầu".' : 'Phần đầu file sẽ được bỏ đi.'
		);
	}

	async function toggleLines(ch: ImportChapter) {
		if (expanded === ch.start_line) {
			expanded = null;
			return;
		}
		expanded = ch.start_line;
		if (!loaded.has(ch.start_line)) await loadMore(ch);
	}

	async function loadMore(ch: ImportChapter) {
		const cur = loaded.get(ch.start_line);
		// Dòng đầu là tiêu đề (trừ chương "Mở đầu" không có dòng tiêu đề riêng).
		const first = boundarySet.has(ch.start_line) ? ch.start_line + 1 : ch.start_line;
		const start = cur ? cur.start + cur.lines.length : first;
		const count = Math.min(LINES_PAGE, ch.end_line - start);
		if (count <= 0) return;
		try {
			const res = await importLines(preview.id, start, count);
			const lines = [...(cur?.lines ?? []), ...res.lines];
			loaded.set(ch.start_line, {
				start: cur?.start ?? first,
				lines,
				done: first + lines.length >= ch.end_line
			});
		} catch (err) {
			fail(err);
		}
	}

	async function save() {
		if (updating) {
			onnext?.();
			return;
		}
		busy = true;
		error = '';
		try {
			const novel = await commitImport(preview.id, {
				title: title.trim() || preview.default_title,
				lang,
				boundaries: preview.boundaries,
				keep_front_matter: keepFront
			});
			onsaved?.(novel);
		} catch (err) {
			fail(err);
		} finally {
			busy = false;
		}
	}

	const fmt = (n: number) => n.toLocaleString('vi-VN');
</script>

<div class="preview" aria-busy={busy}>
	<div class="scroll">
	{#if !updating}
	<label class="field-row">
		Tên truyện
		<input class="field" bind:value={title} placeholder={preview.default_title} maxlength="200" />
	</label>

	<fieldset class="lang">
		<legend>
			Ngôn ngữ của file
			{#if preview.detected_lang === 'unknown'}
				<span class="hint">· không tự nhận ra được, hãy chọn</span>
			{:else}
				<span class="hint">· tự nhận diện: {preview.detected_lang === 'vi' ? 'tiếng Việt' : 'tiếng Trung'}</span>
			{/if}
		</legend>
		<label><input type="radio" name="lang" value="zh" bind:group={lang} /> Tiếng Trung · cần dịch</label>
		<label
			><input type="radio" name="lang" value="vi" bind:group={lang} /> Tiếng Việt · bản dịch có sẵn,
			đọc ngay</label
		>
	</fieldset>
	{/if}

	<div class="summary">
		<p class="count">
			<strong>{fmt(preview.chapters.length)}</strong> chương ·
			{#if totalWarnings}
				<strong class="warn-text">{totalWarnings}</strong> cảnh báo cần xem
			{:else}
				không có cảnh báo
			{/if}
		</p>
		{#if warned.length}
			<label class="filter">
				<input type="checkbox" bind:checked={onlyWarnings} /> Chỉ hiện chương có cảnh báo
			</label>
		{/if}
	</div>

	{#each preview.warnings.filter((w) => w.code === 'no_headings') as w (w.code)}
		<p class="notice notice-warn">{w.message} Bạn có thể mở chương ra và tách tại từng tiêu đề.</p>
	{/each}

	{#if preview.front_matter}
		{@const fm = preview.front_matter}
		<section class="front" aria-labelledby="fm-h">
			<h3 id="fm-h">Phần đầu file <span class="hint">· trước tiêu đề đầu tiên, {fmt(fm.chars)} ký tự</span></h3>
			<p class="excerpt">{fm.excerpt}</p>
			<div class="seg" role="group" aria-label="Xử lý phần đầu file">
				<button
					type="button"
					class="btn"
					aria-pressed={fm.keep}
					disabled={busy}
					onclick={() => !fm.keep && setKeepFront(true)}>Giữ làm chương "Mở đầu"</button
				>
				<button
					type="button"
					class="btn"
					aria-pressed={!fm.keep}
					disabled={busy}
					onclick={() => fm.keep && setKeepFront(false)}>Bỏ đi</button
				>
			</div>
		</section>
	{/if}

	<p role="status" class="sr-status">{status}</p>

	<ol class="chapters">
		{#each shown as ch (ch.start_line)}
			{@const canMerge = boundarySet.has(ch.start_line) && ch.start_line !== preview.boundaries[0]}
			{@const lines = loaded.get(ch.start_line)}
			<li class:has-warn={ch.warnings.length > 0}>
				<div class="row">
					<span class="num">{ch.number}</span>
					<div class="main">
						<span class="t">{ch.title}</span>
						<span class="meta">{fmt(ch.chars)} ký tự · {ch.excerpt}</span>
						{#each ch.warnings as w (w.code)}
							<span class="warn">{w.message}</span>
						{/each}
					</div>
				</div>
				<div class="row-actions">
					<button
						type="button"
						class="btn btn-ghost"
						aria-expanded={expanded === ch.start_line}
						aria-label="Xem các dòng của chương {ch.number}"
						onclick={() => toggleLines(ch)}
						>{expanded === ch.start_line ? 'Ẩn các dòng' : 'Xem các dòng'}</button
					>
					{#if canMerge}
						<button
							type="button"
							class="btn btn-ghost"
							disabled={busy}
							aria-label="Gộp chương {ch.number} vào chương trước"
							onclick={() => merge(ch)}>Gộp vào chương trước</button
						>
					{/if}
				</div>
				{#if expanded === ch.start_line}
					<div class="lines">
						{#if !lines}
							<p class="hint">Đang tải…</p>
						{:else}
							{#each lines.lines as text, i (lines.start + i)}
								{#if text.trim()}
									<div class="line">
										<span>{text}</span>
										<button
											type="button"
											class="btn btn-ghost split"
											disabled={busy}
											aria-label="Tách chương tại dòng: {text.trim().slice(0, 40)}"
											onclick={() => splitAt(lines.start + i, text)}>Tách chương tại đây</button
										>
									</div>
								{/if}
							{/each}
							{#if !lines.done}
								<button type="button" class="btn" onclick={() => loadMore(ch)}>Tải thêm dòng</button>
							{/if}
						{/if}
					</div>
				{/if}
			</li>
		{/each}
	</ol>

	</div>

	{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

	<div class="actions">
		<button type="button" class="btn" onclick={oncancel}>Huỷ</button>
		<button type="button" class="btn btn-primary" disabled={busy} onclick={save}>
			{busy ? 'Đang xử lý…' : updating ? 'Tiếp tục · xem thay đổi' : 'Lưu vào thư viện'}
		</button>
	</div>
</div>

<style>
	.preview {
		flex: 1;
		display: flex;
		flex-direction: column;
		gap: 12px;
		min-width: 0;
		min-height: 0;
	}
	.scroll {
		flex: 1;
		min-height: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
		overflow-y: auto;
		overscroll-behavior: contain;
		/* chừa chỗ cho viền focus của ô nhập */
		padding: 2px;
		margin: -2px;
	}
	.field-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.hint {
		font-size: 13px;
		font-weight: 400;
		color: var(--ink-muted);
	}
	.lang {
		display: flex;
		flex-wrap: wrap;
		gap: 0 16px;
		margin: 0;
		padding: 0;
		border: none;
		font-size: 14px;
	}
	.lang legend {
		margin-bottom: 2px;
		font-weight: 600;
	}
	.lang label,
	.filter {
		display: inline-flex;
		align-items: center;
		gap: 8px;
		min-height: var(--touch);
	}
	.summary {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 4px 16px;
	}
	.count {
		margin: 0;
	}
	.warn-text,
	.warn {
		color: var(--warn-fg);
	}
	.front {
		padding: 12px 14px;
		border: 1px solid var(--line);
		background: var(--field);
	}
	.front h3 {
		margin: 0 0 6px;
		font-family: var(--font-ui);
		font-size: 14px;
	}
	.excerpt {
		margin: 0 0 10px;
		font-size: 14px;
		overflow-wrap: anywhere;
	}
	.seg {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.seg [aria-pressed='true'] {
		border-color: var(--jade);
		color: var(--jade);
		font-weight: 700;
	}
	.sr-status {
		position: absolute;
		width: 1px;
		height: 1px;
		overflow: hidden;
		clip-path: inset(50%);
	}
	.chapters {
		margin: 0;
		padding: 0;
		list-style: none;
		border-top: 1px solid var(--line);
	}
	.chapters > li {
		padding: 10px 0;
		border-bottom: 1px solid var(--line);
		/* Danh sách có thể có hàng nghìn chương: trình duyệt bỏ qua dựng hình phần ngoài màn hình. */
		content-visibility: auto;
		contain-intrinsic-size: auto 96px;
	}
	.chapters > li.has-warn {
		border-left: 3px solid var(--warn-line);
		padding-left: 8px;
	}
	.row {
		display: grid;
		grid-template-columns: 2.6em 1fr;
		gap: 8px;
		font-size: 14px;
	}
	.num {
		color: var(--ink-muted);
	}
	.main {
		display: flex;
		flex-direction: column;
		gap: 2px;
		min-width: 0;
	}
	.t {
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	.meta {
		color: var(--ink-muted);
		font-size: 13px;
		overflow-wrap: anywhere;
	}
	.warn {
		font-size: 13px;
		font-weight: 600;
	}
	.row-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 4px 8px;
		margin: 4px 0 0 calc(2.6em + 8px);
	}
	.row-actions .btn,
	.split {
		min-height: var(--touch);
		font-size: 13px;
	}
	.lines {
		display: flex;
		flex-direction: column;
		gap: 2px;
		margin: 6px 0 0 calc(2.6em + 8px);
		padding-left: 10px;
		border-left: 1px solid var(--line);
		font-size: 13px;
	}
	.line {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		justify-content: space-between;
		gap: 4px 8px;
	}
	.line span {
		flex: 1 1 14em;
		min-width: 0;
		overflow-wrap: anywhere;
	}
	.actions {
		flex: none;
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
		padding-top: 10px;
		border-top: 1px solid var(--line);
	}
	@media (max-width: 480px) {
		.row-actions,
		.lines {
			margin-left: 0;
		}
	}
</style>
