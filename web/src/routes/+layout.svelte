<script lang="ts">
	import '#lib/styles/fonts.js';
	import '#lib/styles/theme.css';
	import favicon from '#lib/assets/favicon.svg';
	import Seal from '#lib/components/Seal.svelte';
	import QuotaPill from '#lib/components/QuotaPill.svelte';
	import { applyPrefs, loadPrefs, prefs } from '#lib/prefs.svelte.js';
	import { page } from '$app/state';
	import { onMount } from 'svelte';
	import type { LayoutProps } from './$types';

	let { children }: LayoutProps = $props();

	// Khu vực kiểu tu tiên luôn đi kèm nhãn rõ nghĩa (design D11).
	const NAV = [
		{ href: '/', xianxia: 'Tàng Thư Các', plain: 'Thư viện' },
		{ href: '/settings', xianxia: 'Thiết Lập', plain: 'Cài đặt' }
	];

	// Trang đăng nhập và reader (toàn màn hình đọc) không có thanh điều hướng chung.
	const isLogin = $derived(page.url.pathname.startsWith('/login'));
	const bare = $derived(isLogin || /^\/novels\/\d+\/chapters\//.test(page.url.pathname));

	function current(href: string): boolean {
		const path = page.url.pathname;
		return href === '/' ? path === '/' || path.startsWith('/novels') : path.startsWith(href);
	}

	onMount(() => {
		applyPrefs(prefs.value);
		if (!isLogin) loadPrefs().catch(() => {});
	});
</script>

<svelte:head>
	<link rel="icon" href={favicon} />
</svelte:head>

{#if bare}
	{@render children()}
{:else}
	<header class="site">
		<a class="brand" href="/">
			<Seal text="译" size={40} />
			<span class="brand-text">
				<span class="name">Novel Translator</span>
				<span class="motto han" aria-hidden="true">译 · 经 · 阁</span>
			</span>
		</a>
		<nav aria-label="Chính">
			{#each NAV as item (item.href)}
				<a href={item.href} aria-current={current(item.href) ? 'page' : undefined}>
					<span class="xianxia">{item.xianxia}</span>
					<span class="plain">{item.plain}</span>
				</a>
			{/each}
		</nav>
		<div class="status"><QuotaPill /></div>
	</header>
	{@render children()}
{/if}

<style>
	.site {
		position: relative;
		z-index: 1;
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px 28px;
		padding: 12px 40px;
		border-bottom: 1px solid var(--line);
		background: var(--paper);
	}
	.brand {
		display: flex;
		align-items: center;
		gap: 12px;
		min-height: var(--touch);
		text-decoration: none;
		color: var(--ink);
	}
	.brand-text {
		display: flex;
		flex-direction: column;
		line-height: 1.1;
	}
	.name {
		font-family: var(--font-title);
		font-size: 24px;
		font-weight: 700;
	}
	.motto {
		font-size: 12px;
		letter-spacing: 0.2em;
		color: var(--label);
	}
	nav {
		display: flex;
		gap: 4px;
	}
	nav a {
		display: flex;
		flex-direction: column;
		justify-content: center;
		min-height: var(--touch);
		padding: 4px 14px;
		border-bottom: 2px solid transparent;
		text-decoration: none;
		color: var(--ink-soft);
	}
	nav a[aria-current='page'] {
		border-bottom-color: var(--cinnabar);
		color: var(--ink);
	}
	.xianxia {
		font-family: var(--font-title);
		font-size: 18px;
		font-weight: 700;
		line-height: 1.1;
	}
	.plain {
		font-size: 12px;
		color: var(--ink-muted);
	}
	.status {
		margin-left: auto;
	}
	@media (max-width: 720px) {
		.site {
			padding: 8px var(--gutter);
			gap: 4px 12px;
		}
		.motto {
			display: none;
		}
		.name {
			font-size: 20px;
		}
		.status {
			margin-left: 0;
			order: 3;
			width: 100%;
		}
		nav {
			margin-left: auto;
		}
		nav a {
			padding: 4px 8px;
		}
	}
</style>
