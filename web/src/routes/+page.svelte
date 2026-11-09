<script lang="ts">
	import { onMount } from 'svelte';
	import { get, logout } from '#lib/api.js';

	type Novel = { id: number; title: string; chapter_count: number; translated_count: number };
	let novels = $state<Novel[] | null>(null);

	onMount(async () => {
		novels = await get<Novel[]>('/api/novels');
	});
</script>

<svelte:head><title>Thư viện</title></svelte:head>

<main>
	<h1>Thư viện</h1>
	{#if novels === null}
		<p>Đang tải…</p>
	{:else if novels.length === 0}
		<p>Chưa có truyện nào.</p>
	{:else}
		<ul>
			{#each novels as n (n.id)}
				<li>{n.title} — {n.translated_count}/{n.chapter_count} chương đã dịch</li>
			{/each}
		</ul>
	{/if}
	<button onclick={logout}>Đăng xuất</button>
</main>
