<script lang="ts">
	// Tạm thời: trang chi tiết truyện đầy đủ ở task 9.4.
	import { page } from '$app/state';
	import { get } from '#lib/api.js';
	import type { Novel } from '#lib/types.js';

	let novel = $state<Novel | null>(null);
	$effect(() => {
		get<Novel>(`/api/novels/${page.params.id}`).then((n) => (novel = n));
	});
</script>

<main style="padding: 24px var(--gutter)">
	<a href="/">← Tàng Thư Các</a>
	{#if novel}<h1>{novel.title}</h1>{/if}
</main>
