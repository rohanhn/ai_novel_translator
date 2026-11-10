<script lang="ts">
	// Bước chọn cách cập nhật và xem thay đổi (spec chapter-update "Explicit update mode",
	// "Change preview"; design D6). Mọi con số do server tính; client chỉ gửi lựa chọn.
	import { SvelteSet } from 'svelte/reactivity';
	import { ApiError } from '../api.js';
	import type {
		ImportPreview,
		UpdateMode,
		UpdatePreview,
		UpdateResult
	} from '../types.js';
	import { applyUpdate, isExpired, previewUpdate, uploadErrorMessage } from './imports.js';

	let {
		preview,
		onapplied,
		onexpired,
		onback,
		oncancel
	}: {
		preview: ImportPreview;
		onapplied: (r: UpdateResult) => void;
		onexpired: (message: string) => void;
		onback: () => void;
		oncancel: () => void;
	} = $props();

	const LIST_LIMIT = 200;

	let mode = $state<UpdateMode | null>(null);
	let start = $state<number | null>(null);
	const toDelete = new SvelteSet<number>();
	let changes = $state<UpdatePreview | null>(null);
	let busy = $state(false);
	let error = $state('');
	let notice = $state('');
	let seq = 0;

	const keepFront = $derived(preview.front_matter ? preview.front_matter.keep : null);
	const canApply = $derived(
		!!mode &&
			!!changes &&
			changes.mode === mode &&
			!busy &&
			!changes.nothing_new &&
			!(changes.needs_start && start == null)
	);

	function body(m: UpdateMode) {
		return {
			mode: m,
			boundaries: preview.boundaries,
			keep_front_matter: keepFront,
			start: m === 'append' ? start : null,
			delete: m === 'replace' ? [...toDelete] : []
		};
	}

	function fail(err: unknown) {
		if (isExpired(err)) onexpired(uploadErrorMessage(err));
		else error = err instanceof ApiError ? err.message : 'Không tính được thay đổi. Thử lại sau.';
	}

	async function refresh() {
		if (!mode) return;
		const my = ++seq;
		busy = true;
		error = '';
		try {
			const res = await previewUpdate(preview.id, body(mode));
			if (my === seq) changes = res;
		} catch (err) {
			if (my === seq) fail(err);
		} finally {
			if (my === seq) busy = false;
		}
	}

	function chooseMode(m: UpdateMode) {
		mode = m;
		notice = '';
		changes = null;
		refresh();
	}

	function setStart(e: Event) {
		const v = (e.currentTarget as HTMLSelectElement).value;
		start = v ? Number(v) : null;
		refresh();
	}

	function toggleDelete(index: number, checked: boolean) {
		if (checked) toDelete.add(index);
		else toDelete.delete(index);
		refresh();
	}

	function setAll(checked: boolean) {
		toDelete.clear();
		if (checked) for (const m of changes?.missing ?? []) toDelete.add(m.index);
		refresh();
	}

	async function confirm() {
		if (!mode || !changes) return;
		busy = true;
		error = '';
		notice = '';
		try {
			onapplied(await applyUpdate(preview.id, { ...body(mode), revision: changes.revision }));
		} catch (err) {
			busy = false;
			if (err instanceof ApiError && err.code === 'stale_preview') {
				notice = 'Truyện vừa thay đổi (có chương vừa dịch hoặc sửa). Hãy xem lại thay đổi bên dưới rồi xác nhận.';
				await refresh();
				return;
			}
			fail(err);
		}
	}

	const fmt = (n: number) => n.toLocaleString('vi-VN');
	const pct = (p: number) => `${Math.round(p * 100)}%`;
	const allSelected = $derived(
		!!changes && changes.missing.length > 0 && changes.missing.every((m) => toDelete.has(m.index))
	);
</script>

<div class="changes" aria-busy={busy}>
	<div class="scroll">
		<fieldset class="modes">
			<legend>Cách cập nhật <span class="hint">· bắt buộc chọn</span></legend>
			<label class="mode" class:on={mode === 'append'}>
				<input type="radio" name="update-mode" value="append" checked={mode === 'append'} onchange={() => chooseMode('append')} />
				<span>
					<strong>Thêm chương mới</strong>
					<span class="hint">Nối các chương sau chương cuối của truyện. Chương đang có không bị đổi.</span>
				</span>
			</label>
			<label class="mode" class:on={mode === 'replace'}>
				<input type="radio" name="update-mode" value="replace" checked={mode === 'replace'} onchange={() => chooseMode('replace')} />
				<span>
					<strong>Tải lại cả bộ</strong>
					<span class="hint">Thứ tự chương theo file. Chương có nội dung gốc không đổi giữ nguyên bản dịch.</span>
				</span>
			</label>
		</fieldset>

		{#if notice}<p role="status" class="notice notice-warn">{notice}</p>{/if}

		{#if !mode}
			<p class="hint">Chọn một cách cập nhật để xem trước thay đổi. Chưa có gì được lưu.</p>
		{:else if !changes}
			<p class="hint">Đang tính thay đổi…</p>
		{:else if changes.mode === 'append'}
			<section class="block" aria-labelledby="append-h">
				<h3 id="append-h">Thay đổi</h3>
				{#if changes.anchor}
					<p>
						Điểm nối: sau chương <strong>{changes.anchor.index}</strong> “{changes.anchor.title}” · chương
						{changes.anchor.position} trong file ({changes.anchor.match === 'content' ? 'trùng nội dung' : 'trùng tiêu đề'}).
					</p>
				{:else if start != null}
					<p>Thêm từ chương {start} trong file, theo lựa chọn của bạn.</p>
				{:else if !changes.needs_start}
					<p>File bắt đầu ngay sau chương cuối của truyện (theo số chương).</p>
				{/if}

				{#each changes.warnings as w (w.code)}
					<p class="notice notice-warn">{w.message}</p>
				{/each}

				{#if changes.needs_start}
					<p class="notice notice-warn">
						Không tìm thấy chương cuối của truyện trong file và không đọc được số chương. Hãy chọn chương
						bắt đầu thêm.
					</p>
				{/if}

				<label class="field-row">
					{changes.needs_start ? 'Bắt đầu thêm từ chương' : 'Đổi điểm bắt đầu (không bắt buộc)'}
					<select class="field" value={start ?? ''} onchange={setStart} disabled={busy}>
						<option value="">{changes.needs_start ? '— Chọn chương —' : 'Tự động'}</option>
						{#each preview.chapters as ch (ch.number)}
							<option value={ch.number}>{ch.number}. {ch.title}</option>
						{/each}
					</select>
				</label>

				{#if changes.nothing_new}
					<p class="notice notice-warn">File không có chương mới nào sau chương cuối của truyện.</p>
				{:else if changes.to_add.length}
					<p class="big"><strong>+{fmt(changes.to_add.length)}</strong> chương mới</p>
					<ol class="list">
						{#each changes.to_add.slice(0, LIST_LIMIT) as c (c.position)}
							<li>{c.title}</li>
						{/each}
						{#if changes.to_add.length > LIST_LIMIT}
							<li class="hint">… và {fmt(changes.to_add.length - LIST_LIMIT)} chương nữa</li>
						{/if}
					</ol>
				{/if}

				{#if changes.differing.length}
					<p class="notice notice-warn">
						{changes.differing.length} chương đang có khác nội dung với file (vd. “{changes.differing[0].title}”).
						Thêm chương mới không đổi các chương này; chọn “Tải lại cả bộ” nếu muốn cập nhật chúng.
					</p>
				{/if}
			</section>
		{:else if changes.counts}
			{@const c = changes.counts}
			<section class="block" aria-labelledby="replace-h">
				<h3 id="replace-h">Thay đổi</h3>
				<dl class="counts">
					<div><dt>Giữ bản dịch</dt><dd>{fmt(c.reuse)}</dd></div>
					<div><dt>Nội dung đổi · dịch lại</dt><dd>{fmt(c.changed)}</dd></div>
					<div><dt>Chương mới</dt><dd>{fmt(c.new)}</dd></div>
					<div><dt>Không còn trong file</dt><dd>{fmt(c.missing)}</dd></div>
				</dl>

				{#if changes.edited_lost.length}
					<div role="alert" class="notice notice-danger">
						<strong>{changes.edited_lost.length} bản sửa tay sẽ mất.</strong> Nội dung gốc của các chương
						này đã đổi nên bản dịch đã sửa tay bị bỏ và chương phải dịch lại:
						<ul>
							{#each changes.edited_lost.slice(0, 20) as e (e.index)}<li>Chương {e.index} · {e.title}</li>{/each}
						</ul>
					</div>
				{/if}

				{#if changes.changed.length}
					<details>
						<summary>Xem {changes.changed.length} chương có nội dung đổi</summary>
						<ol class="list">
							{#each changes.changed.slice(0, LIST_LIMIT) as ch (ch.index)}
								<li>Chương {ch.index} · {ch.title}</li>
							{/each}
						</ol>
					</details>
				{/if}

				{#if changes.missing.length}
					<fieldset class="missing">
						<legend>Chương không còn trong file</legend>
						<p class="hint">
							Chương không chọn sẽ được giữ (cùng bản dịch), đặt ngay sau chương đứng trước nó. Chương được
							chọn sẽ bị xoá cùng bản dịch.
						</p>
						<label class="check all">
							<input type="checkbox" checked={allSelected} disabled={busy} onchange={(e) => setAll(e.currentTarget.checked)} />
							Chọn tất cả để xoá
						</label>
						{#each changes.missing as m (m.index)}
							<label class="check">
								<input
									type="checkbox"
									checked={toDelete.has(m.index)}
									disabled={busy}
									onchange={(e) => toggleDelete(m.index, e.currentTarget.checked)}
								/>
								<span>Xoá chương {m.index} · {m.title}{m.status === 'translated' || m.status === 'edited' ? ' (đã dịch)' : ''}</span>
							</label>
						{/each}
					</fieldset>
				{/if}

				{#if changes.progress}
					{@const p = changes.progress}
					<p>
						Tiến độ đọc: chương {p.from_index} ({pct(p.from_position)}) → chương {p.to_index}
						({pct(p.to_position)})
					</p>
				{/if}
			</section>
		{/if}
	</div>

	{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

	<div class="actions">
		<button type="button" class="btn" disabled={busy} onclick={onback}>Quay lại</button>
		<button type="button" class="btn" onclick={oncancel}>Huỷ</button>
		<button type="button" class="btn btn-primary" disabled={!canApply} onclick={confirm}>
			{busy && changes ? 'Đang xử lý…' : mode === 'replace' ? 'Xác nhận tải lại' : 'Xác nhận thêm chương'}
		</button>
	</div>
</div>

<style>
	.changes {
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
		padding: 2px;
		margin: -2px;
	}
	.hint {
		font-size: 13px;
		font-weight: 400;
		color: var(--ink-muted);
	}
	p {
		margin: 0;
		line-height: 1.55;
		overflow-wrap: anywhere;
	}
	fieldset {
		margin: 0;
		padding: 0;
		border: none;
		min-width: 0;
	}
	legend {
		margin-bottom: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.modes {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
		gap: 10px;
	}
	.modes legend {
		grid-column: 1 / -1;
	}
	.mode {
		display: flex;
		gap: 10px;
		align-items: flex-start;
		min-height: var(--touch);
		padding: 12px;
		border: 1px solid var(--line);
		background: var(--paper-raised);
		cursor: pointer;
	}
	.mode.on {
		border-color: var(--cinnabar);
		box-shadow: inset 0 0 0 1px var(--cinnabar);
	}
	.mode > span {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.mode input {
		margin-top: 3px;
	}
	.block {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	h3 {
		margin: 0;
		font-size: 16px;
	}
	.field-row {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.field-row select {
		min-height: var(--touch);
		max-width: 100%;
	}
	.big {
		font-size: 15px;
	}
	.list {
		margin: 0;
		padding-left: 22px;
		max-height: 240px;
		overflow-y: auto;
		font-size: 14px;
		line-height: 1.6;
		overflow-wrap: anywhere;
	}
	.counts {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
		gap: 8px;
		margin: 0;
	}
	.counts div {
		padding: 10px 12px;
		border: 1px solid var(--line);
		background: var(--paper-raised);
	}
	.counts dt {
		font-size: 13px;
		color: var(--ink-muted);
	}
	.counts dd {
		margin: 2px 0 0;
		font-size: 20px;
		font-weight: 600;
	}
	.notice ul {
		margin: 6px 0 0;
		padding-left: 20px;
	}
	details summary {
		min-height: var(--touch);
		display: flex;
		align-items: center;
		cursor: pointer;
		font-size: 14px;
	}
	.missing {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.check {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: var(--touch);
		font-size: 14px;
		overflow-wrap: anywhere;
	}
	.check input {
		flex: none;
		width: 20px;
		height: 20px;
	}
	.check.all {
		font-weight: 600;
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
	}
</style>
