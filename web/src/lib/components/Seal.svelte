<script lang="ts">
	// Ấn son vuông chứa 1–2 chữ Hán. Trang trí: mặc định ẩn với trình đọc màn hình.
	let {
		text,
		size = 40,
		tone = 'cinnabar',
		label
	}: { text: string; size?: number; tone?: 'cinnabar' | 'ink'; label?: string } = $props();
</script>

<span
	class="seal {tone}"
	class:two={text.length > 1}
	style:--size="{size}px"
	aria-hidden={label ? undefined : 'true'}
	role={label ? 'img' : undefined}
	aria-label={label}>{text}</span
>

<style>
	.seal {
		display: inline-flex;
		flex: none;
		width: var(--size);
		height: var(--size);
		align-items: center;
		justify-content: center;
		font-family: var(--font-han);
		font-size: calc(var(--size) * 0.62);
		line-height: 1;
		border-radius: 3px;
	}
	.two {
		font-size: calc(var(--size) * 0.4);
	}
	.cinnabar {
		background: var(--cinnabar);
		color: var(--on-cinnabar);
		box-shadow:
			inset 0 0 0 2px var(--cinnabar),
			inset 0 0 0 4px var(--paper);
	}
	.ink {
		background: var(--inverse);
		color: var(--on-inverse);
		box-shadow:
			inset 0 0 0 2px var(--inverse),
			inset 0 0 0 3px var(--bronze);
	}
</style>
