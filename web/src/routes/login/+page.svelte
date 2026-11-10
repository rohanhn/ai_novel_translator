<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, login } from '#lib/api.js';
	import InkMountains from '#lib/components/InkMountains.svelte';
	import Seal from '#lib/components/Seal.svelte';

	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	function nextPath(): string {
		const next = page.url.searchParams.get('next') ?? '/';
		// chỉ chuyển trong app, không cho mở redirect ra ngoài
		return next.startsWith('/') && !next.startsWith('//') ? next : '/';
	}

	function message(err: unknown): string {
		if (!(err instanceof ApiError)) return 'Không kết nối được máy chủ. Thử lại sau.';
		if (err.status === 401) return 'Sai mật khẩu.';
		if (err.status === 429) return 'Đăng nhập sai quá nhiều lần. Đăng nhập bị khóa 15 phút, hãy thử lại sau.';
		return err.message;
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await login(password);
		} catch (err) {
			error = message(err);
			password = '';
			busy = false;
			return;
		}
		const next = nextPath();
		// Đã đăng nhập: nếu điều hướng phía client lỗi thì tải lại hẳn trang đích.
		await goto(next, { replaceState: true }).catch(() => location.assign(next));
		busy = false;
	}
</script>

<svelte:head><title>Đăng nhập · Novel Translator</title></svelte:head>

<div class="page">
	<InkMountains position="bottom" height={360} sun />
	<span class="vertical han" aria-hidden="true">译经阁</span>

	<form onsubmit={submit} class="card">
		<div class="intro">
			<Seal text="译" size={64} />
			<h1>Novel Translator</h1>
			<p>Nhập mật khẩu để vào thư viện riêng của bạn</p>
		</div>

		<label>
			Mật khẩu
			<input
				class="field"
				class:invalid={!!error}
				type="password"
				bind:value={password}
				autocomplete="current-password"
				aria-describedby={error ? 'login-err' : undefined}
				aria-invalid={error ? 'true' : undefined}
				required
			/>
		</label>

		{#if error}<p id="login-err" role="alert" class="notice notice-danger">{error}</p>{/if}

		<button type="submit" class="btn btn-primary submit" disabled={busy}>
			{busy ? 'Đang kiểm tra…' : 'Đăng nhập'}
		</button>

		<p class="private">
			<svg aria-hidden="true" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"
				><rect x="4" y="11" width="16" height="10" rx="1" /><path d="M8 11V7a4 4 0 0 1 8 0v4" /></svg
			>
			Trang riêng tư · không cho máy tìm kiếm lập chỉ mục
		</p>
	</form>
</div>

<style>
	.page {
		position: relative;
		min-height: 100dvh;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 48px var(--gutter);
		overflow: hidden;
	}
	.vertical {
		position: absolute;
		top: 60px;
		left: 7%;
		writing-mode: vertical-rl;
		font-size: 64px;
		letter-spacing: 0.2em;
		color: var(--ink);
		opacity: 0.08;
	}
	.card {
		position: relative;
		z-index: 1;
		width: 100%;
		max-width: 420px;
		display: flex;
		flex-direction: column;
		gap: 22px;
		padding: 40px 36px 32px;
		background: var(--paper-raised);
		border: 1px solid var(--line-strong);
		box-shadow:
			inset 0 0 0 6px var(--paper-raised),
			inset 0 0 0 7px var(--line);
	}
	.intro {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 10px;
		text-align: center;
	}
	h1 {
		font-size: 34px;
	}
	.intro p {
		margin: 0;
		font-size: 14px;
		color: var(--ink-muted);
	}
	label {
		display: flex;
		flex-direction: column;
		gap: 8px;
		font-size: 14px;
		font-weight: 600;
	}
	label .field {
		height: 48px;
		font-weight: 400;
	}
	.field.invalid {
		border: 1.5px solid var(--cinnabar);
	}
	.notice {
		margin-top: -8px;
	}
	.submit {
		height: 50px;
		font-size: 16px;
	}
	.private {
		margin: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		font-size: 12px;
		color: var(--ink-muted);
		text-align: center;
	}
	@media (max-width: 480px) {
		.card {
			padding: 32px 20px 24px;
		}
		.vertical {
			display: none;
		}
	}
</style>
