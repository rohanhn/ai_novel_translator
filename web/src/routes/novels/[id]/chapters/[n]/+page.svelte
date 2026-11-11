<script lang="ts">
	import { beforeNavigate } from '$app/navigation';
	import { page } from '$app/state';
	import { untrack } from 'svelte';
	import { ApiError, get, post } from '#lib/api.js';
	import Modal from '#lib/components/Modal.svelte';
	import ChapterEditor from '#lib/reader/ChapterEditor.svelte';
	import ReaderPanel from '#lib/reader/ReaderPanel.svelte';
	import { splitHan } from '#lib/reader/highlight.js';
	import { failureReason, followTranslation, formatReset } from '#lib/reader/stream.js';
	import { ChapterTracker, decisionText, leaveNovel, saveProgress, scrollToRatio } from '#lib/reader/tracker.js';
	import type { Progress } from '#lib/types.js';
	import type { Chapter, ChapterSummary, Novel } from '#lib/types.js';

	type Phase =
		| { kind: 'loading' }
		| { kind: 'ready' }
		| { kind: 'streaming' }
		| { kind: 'failed'; reason: string }
		| { kind: 'quota'; resetAt: string | null }
		| { kind: 'missing' };

	const novelId = $derived(Number(page.params.id));
	const index = $derived(Number(page.params.n));

	let novel = $state<Novel | null>(null);
	let chapters = $state<ChapterSummary[]>([]);
	let chapter = $state<Chapter | null>(null);
	let phase = $state<Phase>({ kind: 'loading' });
	let streamTitle = $state<string | null>(null);
	let streamParas = $state<string[]>([]);
	let waiting = $state<{ delay: number | null } | null>(null);
	let fallbackStep = $state<number | null>(null);
	let showSource = $state(false);
	let panelOpen = $state(false);
	let confirmRetranslate = $state(false);
	let editing = $state(false);
	let stop: (() => void) | null = null;
	let tracker: ChapterTracker | null = null;
	const pretranslated = $derived(!!novel?.pretranslated);
	let prepareMsg = $state('');
	let preparing = $state(false);

	const total = $derived(chapters.length);
	const next = $derived(chapters.find((c) => c.index === index + 1) ?? null);
	const hasTranslation = $derived(
		!!chapter && (chapter.status === 'translated' || chapter.status === 'edited') && chapter.translated_text != null
	);
	const paragraphs = $derived(
		hasTranslation ? chapter!.translated_text!.split('\n').filter((p) => p.trim()) : streamParas
	);
	const sourceParas = $derived(chapter ? chapter.source_text.split('\n').filter((p) => p.trim()) : []);
	const viTitle = $derived(hasTranslation ? chapter!.translated_title : streamTitle);
	// Chữ Hán còn sót cần tô (chỉ với bản dịch đã lưu; lúc đang stream không tô).
	const residue = $derived(new Set(hasTranslation ? (chapter!.untranslated_chars ?? []) : []));

	function detach() {
		stop?.();
		stop = null;
	}

	async function refresh() {
		chapter = await get<Chapter>(`/api/novels/${novelId}/chapters/${index}`);
	}

	function attach(url: string) {
		detach();
		phase = { kind: 'streaming' };
		stop = followTranslation(url, {
			onReset: () => {
				streamTitle = null;
				streamParas = [];
			},
			onTitle: (t) => (streamTitle = t),
			onParagraph: (p) => {
				waiting = null;
				streamParas = [...streamParas, p];
			},
			onWaiting: (delay) => (waiting = { delay }),
			onFallback: (step) => (fallbackStep = step),
			onCompleted: async () => {
				waiting = null;
				await refresh();
				phase = { kind: 'ready' };
			},
			onFailed: (category, message) => {
				waiting = null;
				phase = { kind: 'failed', reason: failureReason(category, message) };
			},
			onQuota: (resetAt) => {
				waiting = null;
				phase = { kind: 'quota', resetAt };
			},
			onCancelled: async () => {
				await refresh();
				phase = chapter?.translated_text ? { kind: 'ready' } : { kind: 'failed', reason: 'Việc dịch đã bị huỷ.' };
			}
		});
	}

	async function translate(opts: { force?: boolean; confirm_discard_edits?: boolean } = {}) {
		streamTitle = null;
		streamParas = [];
		fallbackStep = null;
		try {
			const r = await post<{ stream_url?: string } & Partial<Chapter>>(
				`/api/novels/${novelId}/chapters/${index}/translate`,
				opts
			);
			if (r.stream_url) attach(r.stream_url);
			else {
				chapter = r as Chapter;
				phase = { kind: 'ready' };
			}
		} catch (err) {
			if (err instanceof ApiError && err.status === 429) phase = { kind: 'quota', resetAt: err.resetAt?.toISOString() ?? null };
			else if (err instanceof ApiError && err.code === 'confirmation_required') confirmRetranslate = true;
			else if (err instanceof ApiError) phase = { kind: 'failed', reason: failureReason(err.category ?? 'provider_error', err.message) };
			else phase = { kind: 'failed', reason: 'Không kết nối được máy chủ.' };
		}
	}

	function startTracking(nid: number, n: number, signals: boolean) {
		tracker?.stop();
		prepareMsg = '';
		tracker = new ChapterTracker(
			nid,
			n,
			(d) => {
				const text = decisionText(d);
				if (text) prepareMsg = text;
			},
			signals
		);
		tracker.start();
	}

	async function prepareNext() {
		if (!tracker) return;
		preparing = true;
		try {
			prepareMsg = decisionText(await tracker.explicit());
		} catch {
			prepareMsg = 'Không gửi được yêu cầu. Thử lại sau.';
		} finally {
			preparing = false;
		}
	}

	async function open(nid: number, n: number) {
		detach();
		phase = { kind: 'loading' };
		chapter = null;
		showSource = false;
		editing = false;
		streamTitle = null;
		streamParas = [];
		fallbackStep = null;
		waiting = null;
		let saved: Progress | null = null;
		try {
			const [nv, list, ch, prog] = await Promise.all([
				novel?.id === nid ? Promise.resolve(novel) : get<Novel>(`/api/novels/${nid}`),
				get<ChapterSummary[]>(`/api/novels/${nid}/chapters`),
				get<Chapter>(`/api/novels/${nid}/chapters/${n}`),
				get<Progress | null>(`/api/novels/${nid}/progress`).catch(() => null)
			]);
			novel = nv;
			chapters = list;
			chapter = ch;
			saved = prog;
		} catch (err) {
			if (err instanceof ApiError && err.status === 404) phase = { kind: 'missing' };
			return;
		}
		window.scrollTo(0, 0);
		const ch = chapter!;
		// Ghi nhận đang đọc chương này (vị trí 0 cho tới khi cuộn). Bắt đầu theo dõi ngay khi
		// chương hiện ra (cùng lượt cập nhật DOM), không chờ thêm request nào.
		const resumeAt = saved && saved.chapter_index === n ? saved.position : 0;
		if (!resumeAt) saveProgress(nid, n, 0);
		// Bản dịch có sẵn: không bao giờ gửi tới model → không tín hiệu đọc, không tự dịch.
		const pre = !!novel?.pretranslated;
		startTracking(nid, n, !pre);
		if (pre || ch.status === 'translated' || ch.status === 'edited') {
			phase = { kind: 'ready' };
			// Mở lại đúng chỗ đã dừng (sau khi nội dung đã vẽ).
			if (resumeAt > 0) requestAnimationFrame(() => requestAnimationFrame(() => scrollToRatio(resumeAt)));
		}
		else if (ch.job_lane || ch.status === 'translating')
			attach(`/api/novels/${nid}/chapters/${n}/stream`); // gắn vào job đang chạy (vd. prefetch)
		else if (ch.status === 'failed') phase = { kind: 'failed', reason: 'Lần dịch trước bị lỗi.' };
		else translate(); // chưa dịch: tự dịch, ưu tiên foreground
	}

	$effect(() => {
		const [nid, n] = [novelId, index];
		// Chỉ chạy lại khi đổi chương; state đọc bên trong open() không phải dependency.
		untrack(() => open(nid, n));
		return () => {
			detach();
			tracker?.stop();
			tracker = null;
		};
	});

	// Rời khỏi truyện (sang trang không thuộc truyện này): huỷ prefetch chưa gửi request.
	beforeNavigate(({ to }) => {
		const stay = to?.url.pathname.startsWith(`/novels/${novelId}`);
		if (!stay) leaveNovel(novelId);
	});
</script>

<svelte:head>
	<title>{viTitle ?? chapter?.title ?? 'Đọc truyện'} · {novel?.title ?? ''}</title>
</svelte:head>

<div class="reader">
	<header class="bar">
		<a class="icon" href="/novels/{novelId}" aria-label="Về mục lục">
			<svg aria-hidden="true" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m15 18-6-6 6-6" /></svg>
		</a>
		<span class="novel">{novel?.title ?? ''}</span>
		{#if !editing}
			{#if !pretranslated}<button class="icon han" aria-label={showSource ? 'Xem bản dịch' : 'Xem bản gốc'} title={showSource ? 'Xem bản dịch' : 'Xem bản gốc'} aria-pressed={showSource} onclick={() => (showSource = !showSource)}>原</button>{/if}
			{#if hasTranslation && phase.kind === 'ready'}
				<button class="icon" aria-label="Biên tập bản dịch" onclick={() => { showSource = false; editing = true; }}>
					<svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9" /><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z" /></svg>
				</button>
			{/if}
		{/if}
		<button class="icon han" aria-label="Giao diện đọc" title="Giao diện đọc" aria-expanded={panelOpen} onclick={() => (panelOpen = !panelOpen)}>文</button>
	</header>

	<article class="text" class:wide={editing} lang={showSource ? 'zh' : 'vi'}>
		{#if editing && chapter}
			<h1 class="edit-title">Biên tập · Chương {index}</h1>
			<ChapterEditor
				{novelId}
				{chapter}
				onsaved={(c) => {
					chapter = c;
					editing = false;
				}}
				oncancel={() => (editing = false)}
			/>
		{:else if phase.kind === 'missing'}
			<p role="alert" class="notice notice-danger">Không có chương {index} trong truyện này.</p>
		{:else if chapter}
			<div class="heading">
				{#if !pretranslated}<span class="cn" lang="zh">{chapter.title}</span>{/if}
				{#if !showSource && viTitle}<h1>{#each splitHan(viTitle, residue) as piece, k (k)}{#if piece.mark}<mark class="han-residue">{piece.text}</mark>{:else}{piece.text}{/if}{/each}</h1>{/if}
				<svg class="cloud" aria-hidden="true" width="120" height="14" viewBox="0 0 120 14" fill="none" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"
					><path d="M0 7h44M76 7h44" /><path d="M48 9c2-4 6-4 7-1 1-3 6-4 7 0 2-3 6-3 7 1" /></svg
				>
			</div>

			{#if showSource}
				{#each sourceParas as p, i (i)}<p class="para">{p}</p>{/each}
			{:else}
				{#if phase.kind === 'ready' && chapter}
					<div class="labels">
						{#if pretranslated}
							<p class="notice notice-ok">
								Bản dịch có sẵn{chapter.status === 'edited' ? ' · đã biên tập tay' : ''}. Truyện này được import từ file
								tiếng Việt nên không dịch bằng model.
							</p>
						{:else if chapter.status === 'edited'}
							<p class="notice notice-ok">
								Đã biên tập tay.
								<button class="link" onclick={() => translate({ force: true })}>Dịch lại chương</button>
							</p>
						{/if}
						{#if (chapter.chain_step ?? 1) > 1}
							<p class="notice notice-warn">
								Dịch bằng model dự phòng (bước {chapter.chain_step}{chapter.model ? `, ${chapter.model}` : ''}) vì model chính đã hết lượt.
								<button class="link" onclick={() => translate({ force: true })}>Dịch lại</button>
							</p>
						{/if}
						{#if chapter.glossary_outdated && !pretranslated}
							<p class="notice notice-warn">
								Bộ tên đã đổi sau khi dịch chương này.
								<button class="link" onclick={() => translate({ force: true })}>Dịch lại</button>
							</p>
						{/if}
						{#if chapter.possible_omission}
							<p class="notice notice-warn">
								Có thể thiếu đoạn so với bản gốc.
								<button class="link" onclick={() => (showSource = true)}>Xem bản gốc</button>
							</p>
						{/if}
						{#if chapter.untranslated_han > 0}
							<p class="notice notice-warn" data-testid="untranslated-notice">
								Còn {chapter.untranslated_han} chữ chưa dịch (được tô sáng trong bài).
								<button class="link tap" onclick={() => translate({ force: true })}>Dịch lại</button>
							</p>
						{/if}
					</div>
				{/if}

				{#if phase.kind === 'streaming'}
					<p role="status" class="notice notice-ok streaming">
						<span class="spinner" aria-hidden="true"></span>
						{#if waiting}
							Model tạm hết lượt trong phút này. Tự thử lại{waiting.delay ? ` sau ${Math.round(waiting.delay)} giây` : ''}. Bạn không cần làm gì.
						{:else}
							Đang dịch… đã nhận {streamParas.length} đoạn
						{/if}
					</p>
					{#if fallbackStep}
						<p class="notice notice-warn">Đang dịch bằng model dự phòng (bước {fallbackStep}) vì model chính đã hết lượt hôm nay.</p>
					{/if}
				{/if}

				{#if phase.kind === 'failed'}
					<div role="alert" class="box danger">
						<strong>Dịch lỗi</strong>
						<span>{phase.reason}</span>
						<div class="box-actions">
							<button class="btn btn-primary" onclick={() => translate()}>Thử lại</button>
							<button class="btn" onclick={() => (showSource = true)}>Xem bản gốc</button>
						</div>
					</div>
				{:else if phase.kind === 'quota'}
					<div role="alert" class="box">
						<strong>Hết lượt dịch hôm nay</strong>
						<span>
							Mọi model đã dùng hết lượt theo ngày. Lượt được làm mới lúc <strong>{formatReset(phase.resetAt)}</strong>. Chương này
							vẫn ở trạng thái Chưa dịch; các chương đã dịch đọc bình thường.
						</span>
						<div class="box-actions">
							<button class="btn" onclick={() => (showSource = true)}>Xem bản gốc</button>
							<a class="btn" href="/settings">Xem lượt dùng</a>
						</div>
					</div>
				{/if}

				{#each paragraphs as p, i (i)}<p class="para">{#each splitHan(p, residue) as piece, k (k)}{#if piece.mark}<mark class="han-residue">{piece.text}</mark>{:else}{piece.text}{/if}{/each}</p>{/each}
				{#if phase.kind === 'streaming'}
					<div class="skeleton" aria-hidden="true"><div></div><div></div><div></div></div>
				{/if}
			{/if}
		{:else}
			<p class="muted">Đang tải chương…</p>
		{/if}
	</article>

	<footer class="nav" hidden={editing}>
		{#if prepareMsg}
			<span class="hint" role="status">{prepareMsg}</span>
		{:else if pretranslated}
			<span></span>
		{:else if next && (next.status === 'translated' || next.status === 'edited')}
			<span class="hint">Chương {next.index} đã dịch sẵn</span>
		{:else if next}
			<button class="prepare" disabled={preparing} onclick={prepareNext}>Chuẩn bị chương tiếp</button>
		{/if}
		<nav aria-label="Chuyển chương">
			{#if index > 1}
				<a class="btn" href="/novels/{novelId}/chapters/{index - 1}">‹ Chương {index - 1}</a>
			{:else}
				<button class="btn" disabled>‹ Chương trước</button>
			{/if}
			{#if total && index < total}
				<a class="btn next" href="/novels/{novelId}/chapters/{index + 1}">Chương {index + 1} ›</a>
			{:else}
				<button class="btn next" disabled>Hết chương</button>
			{/if}
		</nav>
	</footer>
</div>

<ReaderPanel bind:open={panelOpen} />

<Modal bind:open={confirmRetranslate} title="Dịch lại chương đã biên tập?" role="alertdialog" tone="danger">
	<p class="confirm-text">
		Bản dịch mới sẽ thay toàn bộ phần bạn đã sửa tay và dùng bộ tên hiện tại. Thao tác tốn 1 lượt dịch
		và không thể hoàn tác.
	</p>
	<div class="box-actions end">
		<button class="btn" onclick={() => (confirmRetranslate = false)}>Giữ bản sửa</button>
		<button
			class="btn btn-primary"
			onclick={() => {
				confirmRetranslate = false;
				translate({ force: true, confirm_discard_edits: true });
			}}>Dịch lại</button
		>
	</div>
</Modal>

<style>
	.reader {
		min-height: 100dvh;
		display: flex;
		flex-direction: column;
	}
	.bar {
		position: sticky;
		top: 0;
		z-index: 10;
		display: flex;
		align-items: center;
		gap: 2px;
		padding: 4px 6px;
		background: var(--paper);
		border-bottom: 1px solid var(--line);
	}
	.icon {
		display: inline-flex;
		width: var(--touch);
		height: var(--touch);
		align-items: center;
		justify-content: center;
		border: none;
		background: transparent;
		color: var(--ink);
		font-size: 22px;
		cursor: pointer;
		text-decoration: none;
	}
	.icon[aria-pressed='true'] {
		background: var(--line);
	}
	.novel {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		font-size: 13px;
		color: var(--ink-muted);
	}
	.text {
		flex: 1;
		width: 100%;
		max-width: 720px;
		margin: 0 auto;
		padding: 20px 24px 32px;
		font-family: var(--font-body);
		font-size: var(--reader-size);
		line-height: var(--reader-leading);
		overflow-wrap: break-word;
	}
	.text.wide {
		max-width: 1200px;
	}
	.edit-title {
		margin-bottom: 16px;
		font-size: 24px;
		color: var(--ink);
	}
	.text[lang='zh'] .para {
		font-family: var(--font-cjk);
	}
	.heading {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 4px;
		margin-bottom: 18px;
		text-align: center;
	}
	.cn {
		font-family: var(--font-han);
		font-size: 26px;
		letter-spacing: 0.08em;
		line-height: 1.3;
	}
	h1 {
		font-size: 22px;
		color: var(--ink-muted);
	}
	.cloud {
		color: var(--bronze);
		margin-top: 4px;
	}
	.han-residue {
		color: var(--residue-fg);
		background: var(--residue-bg);
		text-decoration: underline wavy var(--residue-fg);
		text-decoration-thickness: 1px;
		text-underline-offset: 3px;
		padding: 0 1px;
	}
	.para {
		margin: 0 0 0.9em;
	}
	.labels {
		display: flex;
		flex-direction: column;
		gap: 8px;
		margin-bottom: 14px;
		font-family: var(--font-ui);
	}
	.labels .notice,
	.streaming,
	.text > .notice {
		font-family: var(--font-ui);
		font-size: 13px;
		line-height: 1.45;
		margin-bottom: 14px;
	}
	.link.tap {
		min-height: var(--touch);
	}
	.link {
		min-height: 32px;
		padding: 0 4px;
		border: none;
		background: transparent;
		color: var(--cinnabar);
		font: inherit;
		font-weight: 600;
		text-decoration: underline;
		cursor: pointer;
	}
	.streaming {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.spinner {
		width: 16px;
		height: 16px;
		flex: none;
		border-radius: 50%;
		border: 2px solid var(--jade);
		border-right-color: transparent;
		animation: spin 0.9s linear infinite;
	}
	@keyframes spin {
		to {
			transform: rotate(360deg);
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.spinner {
			animation: none;
		}
	}
	.skeleton {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.skeleton div {
		height: 12px;
		background: var(--paper-sunk);
	}
	.skeleton div:nth-child(2) {
		width: 86%;
	}
	.skeleton div:nth-child(3) {
		width: 64%;
	}
	.box {
		display: flex;
		flex-direction: column;
		gap: 10px;
		margin-bottom: 18px;
		padding: 16px;
		border: 1px solid var(--line-strong);
		background: var(--paper-raised);
		font-family: var(--font-ui);
		font-size: 14px;
		line-height: 1.55;
	}
	.box.danger {
		border-color: var(--danger-line);
		background: var(--danger-bg);
	}
	.box.danger > strong {
		color: var(--danger-fg);
	}
	.box > strong {
		font-size: 15px;
	}
	.box-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 8px;
	}
	.box-actions .btn {
		flex: 1 1 140px;
	}
	.box-actions.end {
		justify-content: flex-end;
	}
	.box-actions.end .btn {
		flex: 0 0 auto;
	}
	.confirm-text {
		margin: 0;
		font-size: 14px;
		line-height: 1.6;
	}
	.nav[hidden] {
		display: none;
	}
	.nav {
		position: sticky;
		bottom: 0;
		display: flex;
		flex-direction: column;
		gap: 6px;
		padding: 8px 16px calc(12px + env(safe-area-inset-bottom));
		background: var(--paper);
		border-top: 1px solid var(--line);
	}
	.prepare {
		align-self: center;
		min-height: var(--touch);
		padding: 0 12px;
		border: none;
		background: transparent;
		color: var(--cinnabar);
		font: inherit;
		font-size: 13px;
		font-weight: 600;
		text-decoration: underline;
		cursor: pointer;
	}
	.hint {
		font-size: 12px;
		color: var(--ink-muted);
		text-align: center;
	}
	nav {
		display: flex;
		gap: 8px;
		max-width: 720px;
		width: 100%;
		margin: 0 auto;
	}
	nav .btn {
		flex: 1;
		border-color: var(--line-strong);
	}
	nav .next:not(:disabled) {
		border-color: var(--cinnabar);
	}
	.muted {
		color: var(--ink-muted);
	}
	@media (max-width: 480px) {
		.text {
			padding: 16px 20px 24px;
		}
	}
</style>
