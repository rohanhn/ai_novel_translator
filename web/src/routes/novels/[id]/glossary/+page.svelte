<script lang="ts">
	import { page } from '$app/state';
	import { ApiError, del, get, post, put } from '#lib/api.js';
	import InkMountains from '#lib/components/InkMountains.svelte';
	import JadeTablet from '#lib/components/JadeTablet.svelte';
	import Modal from '#lib/components/Modal.svelte';
	import ScrollFrame from '#lib/components/ScrollFrame.svelte';
	import type { ChapterSummary, Novel, Suggestion, Term } from '#lib/types.js';

	// Loại tên: cùng bộ từ mà prompt yêu cầu model dùng (pipeline/prompts.py).
	const KINDS = ['nhân vật', 'địa danh', 'môn phái', 'công pháp', 'cảnh giới', 'vật phẩm', 'khác'];

	const id = $derived(Number(page.params.id));
	let novel = $state<Novel | null>(null);
	let terms = $state<Term[]>([]);
	let suggestions = $state<(Suggestion & { draft: string })[]>([]);
	let notFound = $state(false);
	let message = $state('');
	let error = $state('');

	// form thêm/sửa
	let source = $state('');
	let target = $state('');
	let kind = $state('');
	let affected = $state<ChapterSummary[] | null>(null);
	let saving = $state(false);
	let formEl: HTMLElement | undefined = $state();

	const existing = $derived(terms.find((t) => t.source_term === source.trim()) ?? null);
	const renaming = $derived(!!existing && !!target.trim() && existing.target_term !== target.trim());
	const editedCount = $derived(affected?.filter((c) => c.status === 'edited').length ?? 0);
	const translatedCount = $derived((affected?.length ?? 0) - editedCount);

	let removing = $state<Term | null>(null);
	let removeAffected = $state<number | null>(null);
	let removeOpen = $state(false);

	async function load(novelId: number) {
		try {
			const [n, t, s] = await Promise.all([
				get<Novel>(`/api/novels/${novelId}`),
				get<Term[]>(`/api/novels/${novelId}/glossary`),
				get<Suggestion[]>(`/api/novels/${novelId}/suggestions`)
			]);
			novel = n;
			terms = t;
			suggestions = s.map((x) => ({ ...x, draft: x.target_term }));
		} catch (err) {
			if (err instanceof ApiError && err.status === 404) notFound = true;
		}
	}

	$effect(() => {
		load(id);
	});

	// Khi đổi tên một mục đã có: báo trước số chương bị ảnh hưởng.
	$effect(() => {
		const src = existing?.source_term;
		affected = null;
		if (!src) return;
		get<ChapterSummary[]>(`/api/novels/${id}/glossary/${encodeURIComponent(src)}/chapters`)
			.then((c) => (affected = c))
			.catch(() => (affected = []));
	});

	function edit(t: Term) {
		source = t.source_term;
		target = t.target_term;
		kind = t.note ?? '';
		message = '';
		formEl?.scrollIntoView({ behavior: 'smooth', block: 'start' });
	}

	function fail(err: unknown, fallback: string) {
		error = err instanceof ApiError ? err.message : fallback;
	}

	async function save(e: SubmitEvent) {
		e.preventDefault();
		saving = true;
		error = '';
		const wasRename = renaming;
		try {
			await put(`/api/novels/${id}/glossary`, {
				source_term: source.trim(),
				target_term: target.trim(),
				note: kind || null
			});
			message = wasRename
				? `Đã đổi "${source.trim()}" thành "${target.trim()}" và cập nhật các chương đã dịch.`
				: `Đã lưu "${source.trim()}" → "${target.trim()}".`;
			source = target = kind = '';
			await load(id);
		} catch (err) {
			fail(err, 'Không lưu được. Thử lại sau.');
		} finally {
			saving = false;
		}
	}

	async function askRemove(t: Term) {
		removing = t;
		removeAffected = null;
		removeOpen = true;
		const c = await get<ChapterSummary[]>(`/api/novels/${id}/glossary/${encodeURIComponent(t.source_term)}/chapters`).catch(() => []);
		removeAffected = c.length;
	}

	async function confirmRemove() {
		if (!removing) return;
		const t = removing;
		removeOpen = false;
		try {
			await del(`/api/novels/${id}/glossary/${encodeURIComponent(t.source_term)}`);
			message = `Đã xoá "${t.source_term}" khỏi bộ tên.`;
			await load(id);
		} catch (err) {
			fail(err, 'Không xoá được. Thử lại sau.');
		}
	}

	async function accept(s: Suggestion & { draft: string }) {
		error = '';
		try {
			await post(`/api/novels/${id}/suggestions/${encodeURIComponent(s.source_term)}/accept`, {
				target_term: s.draft.trim() || null
			});
			message = `Đã thêm "${s.source_term}" → "${s.draft.trim() || s.target_term}" vào bộ tên.`;
			await load(id);
		} catch (err) {
			fail(err, 'Không lưu được. Thử lại sau.');
		}
	}

	async function dismiss(s: Suggestion) {
		error = '';
		try {
			await post(`/api/novels/${id}/suggestions/${encodeURIComponent(s.source_term)}/dismiss`);
			message = `Đã bỏ qua "${s.source_term}". Tên này sẽ không được đề xuất lại.`;
			await load(id);
		} catch (err) {
			fail(err, 'Không lưu được. Thử lại sau.');
		}
	}
</script>

<svelte:head><title>Danh Lục · Bộ tên · {novel?.title ?? ''}</title></svelte:head>

<div class="page">
	<InkMountains position="top" height={220} />
	<main>
		<a class="back" href="/novels/{id}">← {novel?.title ?? 'Mục lục'}</a>

		{#if notFound}
			<p role="alert" class="notice notice-danger">Không tìm thấy truyện này.</p>
		{:else if novel}
			<div class="intro">
				<h1>Danh Lục <span class="han accent" aria-hidden="true">名录</span><span class="plain">Bộ tên riêng của truyện này</span></h1>
				<p>
					Tên nhân vật, địa danh, cảnh giới, công pháp. Mọi mục được đưa vào lời nhắc dịch để giữ nhất quán. Phiên bản bộ
					tên hiện tại: {novel.glossary_version}.
				</p>
			</div>

			{#if message}<p role="status" class="notice notice-ok">{message}</p>{/if}
			{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}

			<ScrollFrame aria-labelledby="q-h" padding="24px 26px">
				<div class="section-head">
					<h2 id="q-h">Tên mới chờ duyệt · {suggestions.length}</h2>
					<span class="sub">Model đề xuất trong lúc dịch. Tên đã bỏ qua sẽ không được đề xuất lại.</span>
				</div>
				{#if suggestions.length === 0}
					<p class="empty">Không có tên nào chờ duyệt.</p>
				{:else}
					<ul class="queue">
						{#each suggestions as s (s.source_term)}
							<li class="suggestion">
								<span class="src" lang="zh">{s.source_term}</span>
								<label>
									<span class="sr-only">Bản dịch đề xuất cho {s.source_term}</span>
									<span aria-hidden="true" class="small">Bản dịch đề xuất</span>
									<input class="field" bind:value={s.draft} />
								</label>
								{#if s.category}<span class="kind">{s.category}</span>{/if}
								<div class="row-actions">
									<button class="btn btn-primary" onclick={() => accept(s)}>Đồng ý<span class="sr-only"> {s.source_term}</span></button>
									<button class="btn" onclick={() => dismiss(s)}>Bỏ qua<span class="sr-only"> {s.source_term}</span></button>
								</div>
							</li>
						{/each}
					</ul>
					<p class="sub">Sửa ô bản dịch trước khi bấm Đồng ý để lưu theo cách bạn muốn.</p>
				{/if}
			</ScrollFrame>

			<section class="add" aria-labelledby="add-h" bind:this={formEl}>
				<h2 id="add-h">Khắc vào Danh Lục <span class="plain-inline">· thêm hoặc sửa tên</span></h2>
				<form onsubmit={save}>
					<label>Từ gốc<input class="field" lang="zh" bind:value={source} required maxlength="100" /></label>
					<label>Bản dịch<input class="field" bind:value={target} required maxlength="200" /></label>
					<label
						>Loại
						<select class="field" bind:value={kind}>
							<option value="">(không ghi)</option>
							{#each KINDS as k (k)}<option value={k}>{k}</option>{/each}
							{#if kind && !KINDS.includes(kind)}<option value={kind}>{kind}</option>{/if}
						</select>
					</label>
					<button type="submit" class="btn btn-primary" disabled={saving || !source.trim() || !target.trim()}>
						{existing ? 'Lưu thay đổi' : 'Thêm'}
					</button>
				</form>
				{#if renaming && affected}
					<div role="status" class="notice notice-warn impact">
						{#if affected.length === 0}
							Chưa có chương đã dịch nào chứa <span lang="zh">{existing?.source_term}</span>; chỉ các chương dịch sau dùng tên mới.
						{:else}
							<strong>Đổi "{existing?.target_term}" thành "{target.trim()}" sẽ ảnh hưởng {affected.length} chương có chứa <span lang="zh">{existing?.source_term}</span>:</strong>
							{#if translatedCount}<span>• {translatedCount} chương đã dịch: thay "{existing?.target_term}" (nguyên từ) thành "{target.trim()}" và gắn nhãn "Bộ tên đã đổi".</span>{/if}
							{#if editedCount}<span>• {editedCount} chương đã biên tập: giữ nguyên chữ, chỉ gắn nhãn để bạn tự dịch lại.</span>{/if}
						{/if}
					</div>
				{/if}
			</section>

			<section aria-labelledby="list-h">
				<h2 id="list-h" class="list-h">Tên đã lưu · {terms.length}</h2>
				{#if terms.length === 0}
					<p class="empty">Chưa có tên nào. Thêm ở trên hoặc duyệt tên model đề xuất.</p>
				{:else}
					<ul class="tablets">
						{#each terms as t (t.source_term)}
							<li>
								<JadeTablet source={t.source_term} target={t.target_term} note={t.note}>
									{#snippet actions()}
										<button class="btn btn-ghost" onclick={() => edit(t)}>Sửa<span class="sr-only"> {t.source_term}</span></button>
										<button class="btn btn-ghost danger" onclick={() => askRemove(t)}>Xoá<span class="sr-only"> {t.source_term}</span></button>
									{/snippet}
								</JadeTablet>
							</li>
						{/each}
					</ul>
				{/if}
			</section>
		{:else}
			<p class="muted">Đang tải…</p>
		{/if}
	</main>
</div>

<Modal bind:open={removeOpen} title={`Xoá "${removing?.source_term ?? ''}" khỏi bộ tên?`} role="alertdialog" tone="danger">
	<p class="desc">
		{#if removeAffected === null}
			Đang kiểm tra các chương bị ảnh hưởng…
		{:else if removeAffected === 0}
			Chưa có chương đã dịch nào chứa tên này.
		{:else}
			{removeAffected} chương đã dịch có chứa tên này sẽ được gắn nhãn "Bộ tên đã đổi". Chữ trong bản dịch không bị sửa.
		{/if}
		Các chương dịch sau sẽ không còn bắt buộc dùng "{removing?.target_term}".
	</p>
	<div class="dialog-actions">
		<button class="btn" onclick={() => (removeOpen = false)}>Giữ lại</button>
		<button class="btn btn-primary" disabled={removeAffected === null} onclick={confirmRemove}>Xoá tên</button>
	</div>
</Modal>

<style>
	.page {
		position: relative;
	}
	main {
		position: relative;
		z-index: 1;
		max-width: 1100px;
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
	.intro h1 {
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 4px 12px;
		font-size: 42px;
	}
	.accent {
		color: var(--cinnabar);
		font-size: 32px;
	}
	.plain {
		flex-basis: 100%;
		font-family: var(--font-ui);
		font-size: 14px;
		font-weight: 500;
		color: var(--ink-muted);
	}
	.intro p {
		margin: 10px 0 0;
		max-width: 680px;
		color: var(--ink-soft);
		font-size: 14px;
		line-height: 1.6;
	}
	h2 {
		font-size: 26px;
	}
	.plain-inline {
		font-family: var(--font-ui);
		font-size: 14px;
		font-weight: 500;
		color: var(--ink-muted);
	}
	.section-head {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-bottom: 14px;
	}
	.sub,
	.small {
		font-size: 13px;
		color: var(--ink-muted);
	}
	.sub {
		margin: 12px 0 0;
	}
	.section-head .sub {
		margin: 0;
	}
	.queue {
		list-style: none;
		margin: 0;
		padding: 0;
		display: flex;
		flex-direction: column;
	}
	.suggestion {
		display: grid;
		grid-template-columns: 120px minmax(0, 1fr) auto auto;
		align-items: end;
		gap: 8px 16px;
		padding: 12px 0;
		border-top: 1px solid var(--line);
	}
	.suggestion:first-child {
		border-top: none;
	}
	.src {
		align-self: center;
		font-family: var(--font-cjk);
		font-size: 22px;
		font-weight: 500;
	}
	.suggestion label {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.kind {
		align-self: center;
		padding: 2px 8px;
		border: 1px solid var(--line-strong);
		font-size: 12px;
		color: var(--ink-muted);
	}
	.row-actions {
		display: flex;
		gap: 8px;
	}
	.add {
		display: flex;
		flex-direction: column;
		gap: 14px;
	}
	.add form {
		display: grid;
		grid-template-columns: 1fr 1.4fr 1fr auto;
		align-items: end;
		gap: 12px;
	}
	.add label {
		display: flex;
		flex-direction: column;
		gap: 6px;
		font-size: 14px;
		font-weight: 600;
	}
	.add .field {
		font-weight: 400;
	}
	.impact {
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.list-h {
		margin-bottom: 14px;
	}
	.tablets {
		list-style: none;
		margin: 0;
		padding: 0;
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
		gap: 14px;
	}
	.tablets .btn {
		min-height: var(--touch);
		padding: 0 10px;
		margin-left: -10px;
	}
	.danger {
		color: var(--cinnabar);
	}
	.empty,
	.muted {
		margin: 0;
		color: var(--ink-muted);
	}
	.desc {
		margin: 0;
		font-size: 14px;
		line-height: 1.6;
	}
	.dialog-actions {
		display: flex;
		flex-wrap: wrap;
		justify-content: flex-end;
		gap: 10px;
	}
	@media (max-width: 720px) {
		main {
			padding: 12px var(--gutter) 56px;
			gap: 22px;
		}
		.intro h1 {
			font-size: 34px;
		}
		.suggestion {
			grid-template-columns: minmax(0, 1fr) auto;
			grid-template-areas: 'src kind' 'input input' 'actions actions';
			align-items: center;
		}
		.src {
			grid-area: src;
		}
		.kind {
			grid-area: kind;
		}
		.suggestion label {
			grid-area: input;
		}
		.row-actions {
			grid-area: actions;
		}
		.row-actions .btn {
			flex: 1;
		}
		.add form {
			grid-template-columns: 1fr;
		}
	}
</style>
