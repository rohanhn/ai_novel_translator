<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, get } from '#lib/api.js';
	import Cover from '#lib/components/Cover.svelte';
	import InkMountains from '#lib/components/InkMountains.svelte';
	import ScrollFrame from '#lib/components/ScrollFrame.svelte';
	import StatusChip from '#lib/components/StatusChip.svelte';
	import { chipsFor } from '#lib/components/status.js';
	import { hanNumber } from '#lib/han.js';
	import DeleteDialog from '#lib/library/DeleteDialog.svelte';
	import EditNovelDialog from '#lib/library/EditNovelDialog.svelte';
	import { percent, realm } from '#lib/realm.js';
	import type { ChapterSummary, Novel, Progress, Suggestion } from '#lib/types.js';

	type Filter = 'all' | 'done' | 'review' | 'failed';

	const id = $derived(Number(page.params.id));
	let novel = $state<Novel | null>(null);
	let chapters = $state<ChapterSummary[] | null>(null);
	let progress = $state<Progress | null>(null);
	let pending = $state(0);
	let notFound = $state(false);
	let filter = $state<Filter>('all');
	let deleting = $state<Novel | null>(null);
	let editing = $state(false);
	let introOpen = $state(false);

	// Giới thiệu dài (hơn ~6 dòng) được gập lại, có nút "Xem thêm".
	const introLong = $derived(
		!!novel?.description &&
			(novel.description.split('\n').length > 6 || novel.description.length > 420)
	);

	const isDone = (c: ChapterSummary) => c.status === 'translated' || c.status === 'edited';
	const needsReview = (c: ChapterSummary) =>
		c.glossary_outdated || c.possible_omission || (c.chain_step ?? 1) > 1;

	const counts = $derived({
		all: chapters?.length ?? 0,
		done: chapters?.filter(isDone).length ?? 0,
		review: chapters?.filter(needsReview).length ?? 0,
		failed: chapters?.filter((c) => c.status === 'failed').length ?? 0
	});
	const shown = $derived(
		(chapters ?? []).filter((c) =>
			filter === 'done' ? isDone(c) : filter === 'review' ? needsReview(c) : filter === 'failed' ? c.status === 'failed' : true
		)
	);
	const resumeAt = $derived(progress?.chapter_index ?? 1);
	const FILTERS: [Filter, string][] = [
		['all', 'Tất cả'],
		['done', 'Đã dịch'],
		['review', 'Cần xem lại'],
		['failed', 'Lỗi']
	];

	async function load(novelId: number) {
		try {
			[novel, chapters, progress] = await Promise.all([
				get<Novel>(`/api/novels/${novelId}`),
				get<ChapterSummary[]>(`/api/novels/${novelId}/chapters`),
				get<Progress | null>(`/api/novels/${novelId}/progress`)
			]);
			pending = (await get<Suggestion[]>(`/api/novels/${novelId}/suggestions`)).length;
		} catch (err) {
			if (err instanceof ApiError && err.status === 404) notFound = true;
		}
	}

	$effect(() => {
		load(id);
		// Còn chương đang dịch → cập nhật nhãn định kỳ.
		const timer = setInterval(() => {
			if (chapters?.some((c) => c.job_lane || c.status === 'translating')) {
				get<ChapterSummary[]>(`/api/novels/${id}/chapters`).then((c) => (chapters = c));
			}
		}, 4000);
		return () => clearInterval(timer);
	});

	function fmtDate(iso: string): string {
		return new Date(iso).toLocaleString('vi-VN', { dateStyle: 'short', timeStyle: 'short' });
	}

	function action(c: ChapterSummary): string {
		if (c.index === progress?.chapter_index) return 'Đọc tiếp';
		if (c.status === 'failed') return 'Thử lại';
		return 'Đọc';
	}
</script>

<svelte:head><title>{novel?.title ?? 'Truyện'} · Mục lục</title></svelte:head>

<div class="page">
	<InkMountains position="top" height={260} />
	<main>
		<a class="back" href="/">← Tàng Thư Các · Thư viện</a>

		{#if notFound}
			<p role="alert" class="notice notice-danger">Không tìm thấy truyện này. Có thể nó đã bị xoá.</p>
		{:else if novel && chapters}
			<ScrollFrame padding="32px 36px">
				<div class="hero">
					<Cover id={novel.id} title={novel.title} height={220} src={novel.cover_url} />
					<div class="info">
						<div class="heading">
							<h1>{novel.title}</h1>
							{#if novel.author}<p class="author">Tác giả: {novel.author}</p>{/if}
						</div>
						{#if novel.description}
							<div class="intro">
								<!-- nội dung trên một dòng: white-space pre-line giữ mọi xuống dòng -->
								<p id="intro-text" class="intro-text" class:clamped={introLong && !introOpen}>{novel.description}</p>
								{#if introLong}
									<button
										type="button"
										class="btn btn-ghost more"
										aria-expanded={introOpen}
										aria-controls="intro-text"
										onclick={() => (introOpen = !introOpen)}
									>
										{introOpen ? 'Thu gọn' : 'Xem thêm'}
									</button>
								{/if}
							</div>
						{/if}
						<dl>
							<div><dt>Upload lúc</dt><dd>{fmtDate(novel.created_at)}</dd></div>
							{#if novel.pretranslated}
								<div>
									<dt>Nguồn</dt>
									<dd>Bản dịch có sẵn · {counts.all} chương, đọc ngay, không dịch bằng model</dd>
								</div>
							{:else}
								<div>
									<dt>Tu vi · tiến độ dịch</dt>
									<dd><strong class="jade">{realm(counts.done, counts.all)}</strong> · {counts.done} / {counts.all} chương đã dịch</dd>
								</div>
							{/if}
							<div>
								<dt>Đang đọc</dt>
								<dd>
									{#if progress}Chương {progress.chapter_index} · {Math.round(progress.position * 100)}%{:else}Chưa đọc{/if}
								</dd>
							</div>
						</dl>
						<div class="bar" aria-hidden="true"><div style:width="{percent(counts.done, counts.all)}%"></div></div>
						<div class="actions">
							<a class="btn btn-primary" href="/novels/{novel.id}/chapters/{resumeAt}">
								{progress ? `Đọc tiếp · Chương ${resumeAt}` : 'Bắt đầu đọc · Chương 1'}
							</a>
							<a class="btn" href="/novels/{novel.id}/glossary">
								Danh Lục · Bộ tên
								{#if pending}<span class="count" aria-label="{pending} tên chờ duyệt">{pending}</span>{/if}
							</a>
							<button type="button" class="btn btn-ghost" onclick={() => (editing = true)}>
								Sửa thông tin
							</button>
						</div>
					</div>
				</div>
			</ScrollFrame>

			<section class="toc" aria-labelledby="toc-h">
				<div class="toc-head">
					<h2 id="toc-h">Mục lục <span class="han accent" aria-hidden="true">目录</span></h2>
					<div class="filters" role="group" aria-label="Lọc chương">
						{#each FILTERS as [key, label] (key)}
							<button class="filter" aria-pressed={filter === key} onclick={() => (filter = key)}>
								{label} · {counts[key]}
							</button>
						{/each}
					</div>
				</div>

				{#if shown.length === 0}
					<p class="empty">Không có chương nào trong mục này.</p>
				{:else}
					<ol class="rows">
						{#each shown as c (c.index)}
							<li class="row" class:current={c.index === progress?.chapter_index}>
								<span class="num"><span class="han" aria-hidden="true">{hanNumber(c.index)}</span><span class="arabic">Chương {c.index}</span></span>
								<span class="titles">
									<span class="vi">{c.translated_title ?? '—'}</span>
									<span class="cn" lang="zh">{c.title}</span>
								</span>
								<span class="chips">
									{#each chipsFor(c) as kind (kind)}<StatusChip {kind} />{/each}
								</span>
								<a class="go" href="/novels/{id}/chapters/{c.index}">
									{action(c)}<span class="sr-only"> chương {c.index}</span>
								</a>
							</li>
						{/each}
					</ol>
				{/if}
			</section>

			<section class="danger">
				<strong>Xoá truyện</strong>
				<span>Xoá raw, bản dịch, bộ tên, tên chờ duyệt và tiến độ đọc của truyện này. Sẽ hỏi xác nhận trước khi xoá.</span>
				<button class="btn btn-danger" onclick={() => (deleting = novel)}>Xoá truyện…</button>
			</section>
		{:else}
			<p class="muted">Đang tải…</p>
		{/if}
	</main>
</div>

<DeleteDialog bind:novel={deleting} ondeleted={() => goto('/')} />
{#if novel}
	<EditNovelDialog bind:open={editing} {novel} onsaved={(n) => (novel = n)} />
{/if}

<style>
	.page {
		position: relative;
	}
	main {
		position: relative;
		z-index: 1;
		max-width: 1280px;
		margin: 0 auto;
		padding: 24px 40px 72px;
		display: flex;
		flex-direction: column;
		gap: 28px;
	}
	.back {
		align-self: flex-start;
		display: inline-flex;
		align-items: center;
		min-height: var(--touch);
		font-size: 14px;
		text-decoration: none;
	}
	.hero {
		display: flex;
		flex-wrap: wrap;
		gap: 32px;
	}
	.hero :global(.cover) {
		width: 150px;
		flex: none;
	}
	.info {
		flex: 1 1 360px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	h1 {
		font-size: 44px;
		overflow-wrap: anywhere;
	}
	.author {
		margin: 4px 0 0;
		font-size: 15px;
		color: var(--ink-muted);
		overflow-wrap: anywhere;
	}
	.intro {
		display: flex;
		flex-direction: column;
		align-items: flex-start;
		gap: 2px;
		max-width: 68ch;
	}
	.intro-text {
		margin: 0;
		white-space: pre-line;
		font-family: var(--font-body);
		font-size: 15px;
		line-height: 1.65;
		overflow-wrap: anywhere;
	}
	.intro-text.clamped {
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 6;
		line-clamp: 6;
		overflow: hidden;
	}
	.more {
		margin-left: -14px;
	}
	dl {
		margin: 0;
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 12px 24px;
		font-size: 14px;
	}
	dt {
		font-size: 12px;
		letter-spacing: 0.1em;
		text-transform: uppercase;
		color: var(--label);
	}
	dd {
		margin: 3px 0 0;
	}
	.jade {
		color: var(--jade);
	}
	.bar {
		height: 6px;
		max-width: 460px;
		background: var(--paper-sunk);
	}
	.bar div {
		height: 100%;
		background: var(--jade);
	}
	.actions {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.count {
		display: inline-flex;
		min-width: 22px;
		height: 22px;
		padding: 0 6px;
		border-radius: 11px;
		background: var(--cinnabar);
		color: var(--on-cinnabar);
		font-size: 12px;
		align-items: center;
		justify-content: center;
	}
	.toc {
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
	}
	.toc-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px 16px;
		padding: 18px 24px;
		border-bottom: 1px solid var(--line);
	}
	h2 {
		font-size: 28px;
	}
	.accent {
		color: var(--cinnabar);
		font-size: 22px;
	}
	.filters {
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
	}
	.filter {
		min-height: var(--touch);
		padding: 0 12px;
		border: 1px solid var(--line-strong);
		background: transparent;
		color: var(--ink-soft);
		font: inherit;
		font-size: 13px;
		cursor: pointer;
	}
	.filter[aria-pressed='true'] {
		border-color: var(--inverse);
		background: var(--inverse);
		color: var(--on-inverse);
		font-weight: 600;
	}
	.rows {
		list-style: none;
		margin: 0;
		padding: 0;
	}
	.row {
		display: grid;
		grid-template-columns: 110px minmax(0, 1fr) auto auto;
		align-items: center;
		gap: 8px 16px;
		padding: 10px 24px;
		border-top: 1px solid var(--line);
		content-visibility: auto;
		contain-intrinsic-size: auto 64px;
	}
	.row:first-child {
		border-top: none;
	}
	.row.current {
		background: var(--paper-sunk);
	}
	.num {
		display: flex;
		flex-direction: column;
		line-height: 1.2;
	}
	.num .han {
		font-size: 18px;
		color: var(--label);
	}
	.arabic {
		font-size: 12px;
		color: var(--ink-muted);
	}
	.titles {
		display: flex;
		flex-direction: column;
		min-width: 0;
	}
	.vi {
		font-family: var(--font-title);
		font-size: 18px;
		font-weight: 600;
		overflow-wrap: anywhere;
	}
	.cn {
		font-family: var(--font-cjk);
		font-size: 14px;
		color: var(--ink-muted);
	}
	.chips {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 6px;
	}
	.go {
		display: inline-flex;
		align-items: center;
		justify-content: flex-end;
		min-width: var(--touch);
		min-height: var(--touch);
		font-weight: 600;
		font-size: 14px;
		text-decoration: none;
		white-space: nowrap;
	}
	.empty,
	.muted {
		margin: 0;
		padding: 20px 24px;
		color: var(--ink-muted);
	}
	.danger {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px 14px;
		padding: 16px 22px;
		border: 1px solid var(--danger-line);
		background: var(--paper-raised);
	}
	.danger strong {
		font-family: var(--font-title);
		font-size: 20px;
		color: var(--danger-fg);
	}
	.danger span {
		flex: 1 1 300px;
		font-size: 14px;
		color: var(--ink-soft);
	}
	@media (max-width: 720px) {
		main {
			padding: 12px var(--gutter) 56px;
			gap: 20px;
		}
		h1 {
			font-size: 32px;
		}
		.hero {
			gap: 20px;
		}
		.hero :global(.cover) {
			width: 110px;
			height: 160px !important;
		}
		.toc-head {
			padding: 14px var(--gutter);
		}
		.row {
			grid-template-columns: minmax(0, 1fr) auto;
			grid-template-areas: 'num go' 'titles titles' 'chips chips';
			padding: 10px var(--gutter);
			gap: 4px 12px;
		}
		.num {
			grid-area: num;
			flex-direction: row;
			align-items: baseline;
			gap: 8px;
		}
		.titles {
			grid-area: titles;
		}
		.chips {
			grid-area: chips;
			justify-content: flex-start;
		}
		.go {
			grid-area: go;
		}
		.danger {
			padding: 14px var(--gutter);
		}
	}
</style>
