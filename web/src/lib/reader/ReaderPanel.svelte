<script lang="ts">
	// "Giao diện đọc": theme, cỡ chữ, giãn dòng. Lưu server-side, áp dụng mọi thiết bị.
	import { prefs, savePrefs, THEME_NAMES, type Theme } from '../prefs.svelte.js';

	let { open = $bindable(false) }: { open?: boolean } = $props();
	let error = $state('');
	const GLYPH: Record<Theme, string> = { light: '宣', sepia: '卷', dark: '月', bamboo: '竹' };
	const THEMES = Object.keys(THEME_NAMES) as Theme[];

	async function set(changes: Parameters<typeof savePrefs>[0]) {
		error = '';
		try {
			await savePrefs(changes);
		} catch {
			error = 'Không lưu được tùy chọn. Thử lại sau.';
		}
	}
	const size = $derived(prefs.value.font_size);
	const lh = $derived(prefs.value.line_height);
	const round = (x: number) => Math.round(x * 10) / 10;
</script>

{#if open}
	<div class="panel" role="dialog" aria-label="Giao diện đọc">
		<div class="head">
			<span class="han glyph" aria-hidden="true">阅</span>
			<span class="titles"><strong>Giao diện đọc</strong><span>Lưu cho mọi thiết bị</span></span>
			<button class="icon" aria-label="Đóng" onclick={() => (open = false)}>×</button>
		</div>
		<div class="themes">
			{#each THEMES as t (t)}
				<button class="theme" data-theme={t} aria-pressed={prefs.value.theme === t} onclick={() => set({ theme: t })}>
					<span class="han" aria-hidden="true">{GLYPH[t]}</span>{THEME_NAMES[t]}
				</button>
			{/each}
		</div>
		<div class="row">
			<span>Cỡ chữ · {size} px</span>
			<button class="icon" aria-label="Giảm cỡ chữ" disabled={size <= 12} onclick={() => set({ font_size: size - 1 })}>A−</button>
			<button class="icon" aria-label="Tăng cỡ chữ" disabled={size >= 32} onclick={() => set({ font_size: size + 1 })}>A+</button>
		</div>
		<div class="row">
			<span>Giãn dòng · {lh.toFixed(1)}</span>
			<button class="icon" aria-label="Giảm giãn dòng" disabled={lh <= 1.2} onclick={() => set({ line_height: round(lh - 0.1) })}>−</button>
			<button class="icon" aria-label="Tăng giãn dòng" disabled={lh >= 2.4} onclick={() => set({ line_height: round(lh + 0.1) })}>+</button>
		</div>
		{#if error}<p role="alert" class="notice notice-danger">{error}</p>{/if}
	</div>
{/if}

<style>
	.panel {
		position: fixed;
		z-index: 20;
		left: 50%;
		bottom: 12px;
		transform: translateX(-50%);
		width: min(420px, calc(100vw - 2 * var(--gutter)));
		display: flex;
		flex-direction: column;
		gap: 14px;
		padding: 16px;
		background: var(--paper-raised);
		color: var(--ink);
		border: 1px solid var(--line-strong);
		box-shadow: 0 16px 40px var(--shadow);
	}
	.head {
		display: flex;
		align-items: center;
		gap: 10px;
	}
	.glyph {
		font-size: 26px;
		color: var(--cinnabar);
	}
	.titles {
		flex: 1;
		display: flex;
		flex-direction: column;
		font-size: 12px;
		color: var(--ink-muted);
	}
	.titles strong {
		font-size: 15px;
		color: var(--ink);
	}
	.themes {
		display: grid;
		grid-template-columns: repeat(4, minmax(0, 1fr));
		gap: 8px;
	}
	.theme {
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 2px;
		min-height: 60px;
		padding: 6px 2px;
		border: 1px solid var(--line-strong);
		background: var(--paper);
		color: var(--ink);
		font: inherit;
		font-size: 12px;
		cursor: pointer;
	}
	.theme .han {
		font-size: 20px;
	}
	.theme[aria-pressed='true'] {
		outline: 2px solid var(--cinnabar);
		outline-offset: 2px;
	}
	.row {
		display: flex;
		align-items: center;
		gap: 8px;
		font-size: 14px;
	}
	.row span {
		flex: 1;
	}
	.icon {
		width: var(--touch);
		height: var(--touch);
		border: 1px solid var(--line-strong);
		background: transparent;
		color: var(--ink);
		font: inherit;
		font-size: 16px;
		cursor: pointer;
	}
	.head .icon {
		border: none;
		font-size: 22px;
	}
	.icon:disabled {
		opacity: 0.4;
	}
</style>
