<script lang="ts">
	// Thiết Lập · Cài đặt (artboard "Tiên hiệp · Thiết lập"). Tùy chọn lưu server-side nên
	// áp dụng cho mọi thiết bị/trình duyệt đã đăng nhập.
	import { goto } from '$app/navigation';
	import { onMount } from 'svelte';
	import { get, logout } from '#lib/api.js';
	import { hanNumber } from '#lib/han.js';
	import { prefs, savePrefs, THEME_NAMES, type Preferences, type Theme } from '#lib/prefs.svelte.js';
	import { formatReset } from '#lib/reader/stream.js';

	type Step = {
		step: number;
		provider: string;
		model: string;
		requests_today: number;
		exhausted: boolean;
		reset_at: string | null;
	};
	type Quota = { steps: Step[]; provider_override: string | null };
	type AppSettings = { gemini_key_configured: boolean };

	const GLYPH: Record<Theme, string> = { light: '宣', sepia: '卷', dark: '月', bamboo: '竹' };
	const THEMES = Object.keys(THEME_NAMES) as Theme[];

	let quota = $state<Quota | null>(null);
	let quotaError = $state('');
	let keyConfigured = $state<boolean | null>(null);
	let error = $state('');
	let saved = $state('');
	let leaving = $state(false);

	// Thanh trượt cập nhật xem trước ngay khi kéo; chỉ lưu khi thả (sự kiện change).
	let size = $state(prefs.value.font_size);
	let lh = $state(prefs.value.line_height);
	$effect(() => {
		size = prefs.value.font_size;
		lh = prefs.value.line_height;
	});

	onMount(async () => {
		try {
			const [q, s] = await Promise.all([get<Quota>('/api/settings/quota'), get<AppSettings>('/api/settings')]);
			quota = q;
			keyConfigured = s.gemini_key_configured;
		} catch {
			quotaError = 'Không tải được tình trạng lượt dùng. Thử lại sau.';
		}
	});

	async function set(changes: Partial<Preferences>, what: string) {
		error = '';
		saved = '';
		try {
			await savePrefs(changes);
			saved = `Đã lưu ${what}.`;
		} catch {
			error = 'Không lưu được tùy chọn. Thử lại sau.';
			size = prefs.value.font_size;
			lh = prefs.value.line_height;
		}
	}

	async function signOut() {
		leaving = true;
		try {
			await logout();
		} finally {
			await goto('/login');
		}
	}

	const previewTheme = $derived(prefs.value.theme);
</script>

<svelte:head><title>Cài đặt · Novel Translator</title></svelte:head>

<main>
	<h1>
		<span class="xianxia">Thiết Lập</span>
		<span class="han" aria-hidden="true">设定</span>
		<span class="plain">Cài đặt</span>
	</h1>

	<section class="card reading" aria-labelledby="doc-h">
		<div class="controls">
			<div>
				<h2 id="doc-h">Giao diện đọc</h2>
				<p class="sub">Lưu trên máy chủ, áp dụng cho mọi thiết bị bạn đăng nhập.</p>
			</div>
			<fieldset>
				<legend>Nền giấy</legend>
				<div class="themes">
					{#each THEMES as t (t)}
						<button
							type="button"
							class="theme"
							aria-pressed={prefs.value.theme === t}
							onclick={() => set({ theme: t }, `nền ${THEME_NAMES[t]}`)}
						>
							<span class="swatch han" data-theme={t} aria-hidden="true">{GLYPH[t]}</span>
							{THEME_NAMES[t]}
						</button>
					{/each}
				</div>
			</fieldset>
			<label>
				Cỡ chữ · {size} px
				<input
					type="range"
					min="12"
					max="32"
					step="1"
					bind:value={size}
					onchange={() => set({ font_size: size }, 'cỡ chữ')}
				/>
			</label>
			<label>
				Giãn dòng · {lh.toFixed(1)}
				<input
					type="range"
					min="1.2"
					max="2.4"
					step="0.1"
					bind:value={lh}
					onchange={() => set({ line_height: Math.round(lh * 10) / 10 }, 'giãn dòng')}
				/>
			</label>
			<p class="saved" role="status">{saved}</p>
			{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}
		</div>
		<div class="preview" data-theme={previewTheme} aria-label="Xem trước" style:--size="{size}px" style:--lh={lh}>
			<p class="eyebrow">Xem trước</p>
			<p>
				Sáng sớm, trấn Thanh Dương chìm trong làn sương mỏng. Lâm Động dậy từ sớm, một mình đi lên khoảng
				đất trống ở núi sau, ngồi xếp bằng hô hấp nguyên lực giữa thiên địa.
			</p>
		</div>
	</section>

	<section class="card prefetch" aria-labelledby="pf-h">
		<div class="text">
			<h2 id="pf-h">Chuẩn bị trước chương kế</h2>
			<p>
				Khi bạn đọc một chương ít nhất 30 giây hoặc cuộn quá 60%, hệ thống dịch sẵn chương kế tiếp. Chỉ dùng
				lượt của model chính; khi model chính hết lượt hôm nay thì tạm dừng để dành lượt cho chương bạn mở.
			</p>
		</div>
		<label class="switch">
			<input
				type="checkbox"
				role="switch"
				checked={prefs.value.prefetch}
				onchange={(e) =>
					set({ prefetch: e.currentTarget.checked }, e.currentTarget.checked ? 'bật chuẩn bị trước' : 'tắt chuẩn bị trước')}
			/>
			{prefs.value.prefetch ? 'Đang bật' : 'Đang tắt'}
		</label>
	</section>

	<section class="quota" aria-labelledby="q-h">
		<h2 id="q-h"><span class="xianxia">Pháp khí ·</span> Chuỗi model và lượt dùng hôm nay</h2>
		{#if quotaError}
			<p role="alert">{quotaError}</p>
		{:else if !quota}
			<p>Đang tải…</p>
		{:else}
			{#if quota.provider_override}
				<p class="override">
					Đang dùng provider <strong>{quota.provider_override}</strong> (ghi đè bằng biến môi trường), chuỗi
					model dưới đây không được dùng.
				</p>
			{/if}
			<div class="scroll">
				<table>
					<thead>
						<tr>
							<th scope="col">Bước</th>
							<th scope="col">Model</th>
							<th scope="col">Lượt đã dùng hôm nay</th>
							<th scope="col">Trạng thái</th>
						</tr>
					</thead>
					<tbody>
						{#each quota.steps as s (s.step)}
							<tr>
								<td class="step"><span class="han" aria-hidden="true">{hanNumber(s.step)}</span><span class="sr-only">Bước {s.step}</span></td>
								<td>
									{s.provider} · {s.model}
									<span class="role">
										{s.step === 1 ? 'Dùng cho chương bạn mở và chuẩn bị trước' : 'Dự phòng, chỉ cho chương bạn mở'}
									</span>
								</td>
								<td class="num"><span class="mlabel">Lượt đã dùng hôm nay:</span>{" "}{s.requests_today}</td>
								<td>
									<span class="state" class:out={s.exhausted}>
										{s.exhausted ? `Hết lượt hôm nay · làm mới lúc ${formatReset(s.reset_at)}` : 'Còn lượt'}
									</span>
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
		<p class="foot">
			Lượt theo ngày được làm mới lúc 0:00 giờ Thái Bình Dương (15:00 giờ Việt Nam, 14:00 khi Mỹ dùng giờ mùa
			hè). App chỉ đếm số lượt đã dùng thực tế, không tự ghi giới hạn của Google. Model cấu hình qua biến môi
			trường <code>NT_CHAIN</code>.
			{#if keyConfigured === false}<strong>Chưa cấu hình key Gemini.</strong>{/if}
		</p>
	</section>

	<section class="card data">
		<p>
			<strong>Về dữ liệu:</strong> app dùng Gemini API gói miễn phí bằng key của bạn. Ở gói miễn phí, Google có thể
			dùng nội dung gửi lên để cải thiện sản phẩm của họ.
		</p>
	</section>

	<div class="signout">
		<button class="btn" onclick={signOut} disabled={leaving}>{leaving ? 'Đang đăng xuất…' : 'Đăng xuất'}</button>
	</div>
</main>

<style>
	main {
		max-width: 1100px;
		margin: 0 auto;
		padding: 28px var(--gutter) 72px;
		display: flex;
		flex-direction: column;
		gap: 24px;
	}
	h1 {
		margin: 0;
		display: flex;
		flex-wrap: wrap;
		align-items: baseline;
		gap: 6px 14px;
		font-family: var(--font-title);
		font-size: clamp(32px, 7vw, 42px);
		line-height: 1.1;
	}
	h1 .han {
		font-size: 0.75em;
		font-weight: 400;
		color: var(--cinnabar);
	}
	h1 .plain {
		font-family: var(--font-ui);
		font-size: 15px;
		font-weight: 500;
		color: var(--ink-soft);
	}
	h2 {
		margin: 0;
		font-family: var(--font-title);
		font-size: 26px;
	}
	.card {
		padding: 22px 24px;
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
	}
	.reading {
		display: flex;
		flex-wrap: wrap;
		gap: 28px;
	}
	.controls {
		flex: 1 1 380px;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 18px;
	}
	.sub {
		margin: 4px 0 0;
		font-size: 13px;
		color: var(--ink-soft);
	}
	fieldset {
		margin: 0;
		padding: 0;
		border: none;
		display: flex;
		flex-direction: column;
		gap: 10px;
	}
	legend,
	label {
		font-size: 13px;
		font-weight: 600;
	}
	legend {
		margin-bottom: 10px;
	}
	.themes {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 10px;
	}
	.theme {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
		padding: 0 0 4px;
		border: none;
		background: transparent;
		color: var(--ink);
		font: inherit;
		font-size: 12px;
		cursor: pointer;
	}
	.swatch {
		width: 100%;
		max-width: 72px;
		height: 84px;
		display: flex;
		align-items: center;
		justify-content: center;
		font-size: 28px;
		background: var(--paper);
		color: var(--ink);
		box-shadow: inset 0 0 0 1px var(--line-strong);
	}
	.theme[aria-pressed='true'] .swatch {
		box-shadow:
			0 0 0 2px var(--paper-raised),
			0 0 0 4px var(--cinnabar);
	}
	.theme[aria-pressed='true'] {
		font-weight: 700;
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	input[type='range'] {
		height: var(--touch);
		accent-color: var(--cinnabar);
	}
	.saved {
		margin: 0;
		min-height: 1.2em;
		font-size: 13px;
		color: var(--ok-fg);
	}
	.preview {
		flex: 1 1 320px;
		min-width: 0;
		padding: 24px;
		background: var(--paper);
		color: var(--ink);
		box-shadow: inset 0 0 0 1px var(--line);
		font-family: var(--font-body);
		font-size: var(--size);
		line-height: var(--lh);
	}
	.preview p {
		margin: 0;
	}
	.preview .eyebrow {
		margin-bottom: 0.8em;
		font-family: var(--font-ui);
		font-size: 12px;
		line-height: 1.4;
	}
	.prefetch {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 16px;
	}
	.prefetch .text {
		flex: 1 1 420px;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.prefetch h2 {
		font-size: 24px;
	}
	.prefetch p {
		margin: 0;
		font-size: 14px;
		line-height: 1.55;
		color: var(--ink-soft);
	}
	.switch {
		flex-direction: row;
		align-items: center;
		gap: 12px;
		min-height: var(--touch);
		font-size: 14px;
		cursor: pointer;
	}
	.switch input {
		width: 22px;
		height: 22px;
		accent-color: var(--jade);
	}
	.quota {
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 22px 24px;
		background: var(--inverse);
		color: var(--on-inverse);
		box-shadow:
			inset 0 0 0 5px var(--inverse),
			inset 0 0 0 6px var(--bronze);
	}
	.quota p {
		margin: 0;
	}
	.override {
		font-size: 14px;
	}
	.scroll {
		overflow-x: auto;
	}
	table {
		width: 100%;
		min-width: 560px;
		border-collapse: collapse;
		font-size: 14px;
	}
	th {
		padding: 10px 12px;
		text-align: left;
		font-weight: 600;
		border-bottom: 1px solid var(--bronze);
	}
	td {
		padding: 14px 12px;
		vertical-align: top;
		border-bottom: 1px solid color-mix(in srgb, var(--on-inverse) 15%, transparent);
	}
	th:first-child,
	td:first-child {
		padding-left: 0;
	}
	.step .han {
		font-size: 22px;
	}
	.role {
		display: block;
		font-size: 12px;
		opacity: 0.85;
	}
	.num {
		font-variant-numeric: tabular-nums;
	}
	.state {
		display: inline-block;
		text-align: left;
		padding: 3px 10px;
		border: 1px solid var(--jade);
		font-size: 12px;
		font-weight: 600;
	}
	.state.out {
		border-color: var(--cinnabar);
	}
	.foot {
		font-size: 13px;
		line-height: 1.55;
		opacity: 0.9;
	}
	.data p {
		margin: 0;
		font-size: 14px;
		line-height: 1.55;
	}
	.signout {
		display: flex;
		justify-content: flex-end;
	}
	.signout .btn {
		min-width: 140px;
	}
	.mlabel {
		display: none;
	}
	@media (max-width: 640px) {
		table,
		tbody {
			display: block;
			min-width: 0;
		}
		thead {
			position: absolute;
			width: 1px;
			height: 1px;
			overflow: hidden;
			clip: rect(0 0 0 0);
		}
		tr {
			display: grid;
			grid-template-columns: 40px minmax(0, 1fr);
			gap: 6px 10px;
			padding: 14px 0;
			border-bottom: 1px solid color-mix(in srgb, var(--on-inverse) 15%, transparent);
		}
		td {
			grid-column: 2;
			padding: 0;
			border: none;
		}
		td.step {
			grid-column: 1;
			grid-row: 1 / span 3;
		}
		.mlabel {
			display: inline;
		}
	}
	@media (max-width: 480px) {
		.card,
		.quota {
			padding: 18px 16px;
		}
		.signout .btn {
			width: 100%;
		}
	}
</style>
