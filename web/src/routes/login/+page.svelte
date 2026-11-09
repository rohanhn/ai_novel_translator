<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import { ApiError, login } from '#lib/api.js';

	let password = $state('');
	let error = $state('');
	let busy = $state(false);

	function nextPath(): string {
		const next = page.url.searchParams.get('next') ?? '/';
		// chỉ chuyển trong app, không cho mở redirect ra ngoài
		return next.startsWith('/') && !next.startsWith('//') ? next : '/';
	}

	async function submit(e: SubmitEvent) {
		e.preventDefault();
		busy = true;
		error = '';
		try {
			await login(password);
			await goto(nextPath(), { replaceState: true });
		} catch (err) {
			error = err instanceof ApiError ? err.message : 'Không kết nối được máy chủ.';
		} finally {
			busy = false;
		}
	}
</script>

<svelte:head><title>Đăng nhập</title></svelte:head>

<main>
	<h1>Đăng nhập</h1>
	<form onsubmit={submit}>
		<label>
			Mật khẩu
			<input type="password" bind:value={password} autocomplete="current-password" required />
		</label>
		<button type="submit" disabled={busy}>Vào</button>
		{#if error}<p role="alert">{error}</p>{/if}
	</form>
</main>
