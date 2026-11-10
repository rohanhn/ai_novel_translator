<script lang="ts">
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { get } from '#lib/api.js';
	import Cover from '#lib/components/Cover.svelte';
	import InkMountains from '#lib/components/InkMountains.svelte';
	import ScrollFrame from '#lib/components/ScrollFrame.svelte';
	import DeleteDialog from '#lib/library/DeleteDialog.svelte';
	import UploadDialog from '#lib/library/UploadDialog.svelte';
	import { percent, realm } from '#lib/realm.js';
	import type { Chapter, LibraryItem, Progress, Suggestion } from '#lib/types.js';

	let novels = $state<LibraryItem[] | null>(null);
	let loadError = $state('');
	let query = $state('');
	let uploadOpen = $state(false);
	let deleting = $state<LibraryItem | null>(null);
	let hero = $state<{ chapter: Chapter | null; progress: Progress | null; pending: number } | null>(null);

	// Truyện đọc gần nhất (API đã xếp đọc gần nhất lên đầu).
	const current = $derived(novels?.find((n) => n.last_read_chapter != null) ?? null);
	// Tìm theo tên hoặc tác giả, không phân biệt hoa thường.
	const visible = $derived.by(() => {
		const q = query.trim().toLowerCase();
		return (novels ?? []).filter(
			(n) => n.title.toLowerCase().includes(q) || (n.author ?? '').toLowerCase().includes(q)
		);
	});

	async function load() {
		try {
			novels = await get<LibraryItem[]>('/api/novels');
			loadError = '';
		} catch {
			loadError = 'Không tải được thư viện. Thử tải lại trang.';
		}
	}

	$effect(() => {
		const n = current;
		if (!n || n.last_read_chapter == null) {
			hero = null;
			return;
		}
		const index = n.last_read_chapter;
		Promise.all([
			get<Chapter>(`/api/novels/${n.id}/chapters/${index}`).catch(() => null),
			get<Progress | null>(`/api/novels/${n.id}/progress`).catch(() => null),
			get<Suggestion[]>(`/api/novels/${n.id}/suggestions`).catch(() => [])
		]).then(([chapter, progress, suggestions]) => {
			hero = { chapter, progress, pending: suggestions.length };
		});
	});

	onMount(load);

	function chapterLabel(c: Chapter | null, index: number): string {
		const name = c?.translated_title ?? c?.title;
		return name ? `Chương ${index}: ${name}` : `Chương ${index}`;
	}
</script>

<svelte:head><title>Tàng Thư Các · Thư viện</title></svelte:head>

<div class="page">
	<InkMountains position="top" height={260} />
	<main>
		{#if current && current.last_read_chapter != null}
			<ScrollFrame aria-labelledby="hero-h" padding="32px 36px">
				<div class="hero">
					<Cover id={current.id} title={current.title} height={220} src={current.cover_url} />
					<div class="hero-body">
						<span id="hero-h" class="eyebrow">Tiếp tục tu luyện · đọc tiếp</span>
						<h1>{current.title}</h1>
						{#if current.author}<p class="author">{current.author}</p>{/if}
						<p class="where">
							Đang ở <strong>{chapterLabel(hero?.chapter ?? null, current.last_read_chapter)}</strong>
							{#if hero?.progress}· đã đọc {Math.round(hero.progress.position * 100)}%{/if}
						</p>
						<div class="progress">
							<div class="progress-text">
								<span>Tu vi · <strong>{realm(current.translated_count, current.chapter_count)}</strong></span>
								<span>{current.translated_count} / {current.chapter_count} chương đã dịch</span>
							</div>
							<div class="bar" aria-hidden="true">
								<div style:width="{percent(current.translated_count, current.chapter_count)}%"></div>
							</div>
						</div>
						<div class="hero-actions">
							<a class="btn btn-primary" href="/novels/{current.id}/chapters/{current.last_read_chapter}">Đọc tiếp</a>
							<a class="btn" href="/novels/{current.id}">Mục lục</a>
							{#if hero?.pending}
								<a class="btn btn-ghost" href="/novels/{current.id}/glossary">
									<span class="count">{hero.pending}</span> tên mới chờ duyệt
								</a>
							{/if}
						</div>
					</div>
				</div>
			</ScrollFrame>
		{/if}

		<div class="toolbar">
			<h2>Kho truyện <span class="han accent" aria-hidden="true">藏书</span></h2>
			<span class="private">
				<svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
					><rect x="4" y="11" width="16" height="10" rx="1" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg
				>
				Chỉ bạn xem được
			</span>
			<div class="tools">
				<label class="search">
					<svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
						><circle cx="11" cy="11" r="7" /><path d="m20 20-3.5-3.5" /></svg
					>
					<span class="sr-only">Tìm truyện</span>
					<input type="search" bind:value={query} placeholder="Tìm tên hoặc tác giả…" />
				</label>
				<button class="btn btn-ink" onclick={() => (uploadOpen = true)}>
					<svg aria-hidden="true" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"
						><path d="M12 5v14M5 12h14" /></svg
					>
					Upload .txt
				</button>
			</div>
		</div>

		{#if loadError}
			<p role="alert" class="notice notice-danger">{loadError}</p>
		{:else if novels === null}
			<p class="muted">Đang tải thư viện…</p>
		{:else if novels.length === 0}
			<ScrollFrame>
				<p class="empty">Thư viện còn trống. Upload một file .txt để bắt đầu đọc.</p>
			</ScrollFrame>
		{:else if visible.length === 0}
			<p class="muted">Không có truyện nào khớp "{query}".</p>
		{:else}
			<ul class="grid">
				{#each visible as n (n.id)}
					<li class="card">
						<a class="card-link" href="/novels/{n.id}">
							<Cover id={n.id} title={n.title} src={n.cover_url} />
							<strong class="card-title">{n.title}</strong>
							{#if n.author}<span class="card-author">{n.author}</span>{/if}
						</a>
						<div class="card-progress">
							<div class="progress-text">
								<span>Tu vi · <strong>{realm(n.translated_count, n.chapter_count)}</strong></span>
								<span>{n.translated_count} / {n.chapter_count} chương</span>
							</div>
							<div class="bar thin" aria-hidden="true">
								<div style:width="{percent(n.translated_count, n.chapter_count)}%"></div>
							</div>
						</div>
						<button class="btn btn-ghost delete" aria-label="Xoá {n.title}" onclick={() => (deleting = n)}>
							Xoá…
						</button>
					</li>
				{/each}
			</ul>
		{/if}
	</main>
</div>

<UploadDialog bind:open={uploadOpen} onuploaded={(n) => goto(`/novels/${n.id}`)} />
<DeleteDialog bind:novel={deleting} ondeleted={() => load()} />

<style>
	.page {
		position: relative;
	}
	main {
		position: relative;
		z-index: 1;
		max-width: 1280px;
		margin: 0 auto;
		padding: 36px 40px 72px;
		display: flex;
		flex-direction: column;
		gap: 36px;
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
	.hero-body {
		flex: 1 1 320px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		justify-content: center;
		gap: 12px;
	}
	h1 {
		font-size: 44px;
		overflow-wrap: anywhere;
	}
	.where {
		margin: 0;
		font-size: 16px;
		color: var(--ink-soft);
	}
	.progress {
		display: flex;
		flex-direction: column;
		gap: 6px;
		max-width: 460px;
	}
	.progress-text {
		display: flex;
		flex-wrap: wrap;
		justify-content: space-between;
		gap: 4px 12px;
		font-size: 13px;
		color: var(--ink-muted);
	}
	.progress-text strong {
		color: var(--jade);
	}
	.bar {
		height: 8px;
		background: var(--paper-sunk);
		border: 1px solid var(--line-strong);
	}
	.bar.thin {
		height: 5px;
		border: none;
	}
	.bar div {
		height: 100%;
		background: var(--jade);
	}
	.hero-actions {
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
		margin-top: 6px;
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
	.toolbar {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 12px 16px;
	}
	h2 {
		font-size: 30px;
	}
	.accent {
		color: var(--cinnabar);
		font-size: 26px;
	}
	.private {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		font-size: 13px;
		color: var(--ink-muted);
	}
	.tools {
		margin-left: auto;
		display: flex;
		flex-wrap: wrap;
		gap: 10px;
	}
	.search {
		display: flex;
		align-items: center;
		gap: 8px;
		min-height: var(--touch);
		padding: 0 14px;
		min-width: 220px;
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
		color: var(--ink-muted);
	}
	.search input {
		flex: 1;
		min-width: 0;
		border: none;
		outline: none;
		background: transparent;
		color: var(--ink);
		font: inherit;
		font-size: 16px;
	}
	.search:focus-within {
		outline: 2px solid var(--cinnabar);
		outline-offset: 2px;
	}
	.grid {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
		gap: 28px 24px;
	}
	.card {
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	.card-link {
		display: flex;
		flex-direction: column;
		gap: 12px;
		color: var(--ink);
		text-decoration: none;
	}
	.card-title {
		font-family: var(--font-title);
		font-size: 21px;
		line-height: 1.15;
		overflow-wrap: anywhere;
	}
	.card-author,
	.author {
		margin: -6px 0 0;
		font-size: 13px;
		color: var(--ink-muted);
		overflow-wrap: anywhere;
	}
	.author {
		margin: 2px 0 0;
		font-size: 15px;
	}
	.card-link:hover .card-title {
		color: var(--cinnabar);
	}
	.card-progress {
		display: flex;
		flex-direction: column;
		gap: 5px;
	}
	.delete {
		align-self: flex-start;
		margin-left: -14px;
		color: var(--cinnabar);
		font-weight: 500;
	}
	.muted,
	.empty {
		margin: 0;
		color: var(--ink-muted);
	}
	@media (max-width: 720px) {
		main {
			padding: 20px var(--gutter) 56px;
			gap: 24px;
		}
		h1 {
			font-size: 34px;
		}
		.hero {
			gap: 20px;
		}
		.hero :global(.cover) {
			width: 110px;
		}
		.tools {
			margin-left: 0;
			width: 100%;
		}
		.search {
			flex: 1 1 100%;
			min-width: 0;
		}
		.tools .btn {
			flex: 1;
		}
		.grid {
			grid-template-columns: repeat(2, minmax(0, 1fr));
			gap: 20px 14px;
		}
		.card :global(.cover) {
			height: 200px !important;
		}
	}
</style>
