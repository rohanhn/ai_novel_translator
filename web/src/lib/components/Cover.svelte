<script lang="ts">
	// Bìa truyện: màu theo id, ấn son chứa chữ đầu của tên.
	let { id, title, height = 260 }: { id: number; title: string; height?: number } = $props();
	const color = $derived(`var(--cover-${(id % 5) + 1})`);
	const initial = $derived(title.trim().charAt(0).toUpperCase() || '?');
</script>

<div class="cover" style:--c={color} style:height="{height}px" aria-hidden="true">
	<span class="title">{title}</span>
	<span class="seal">{initial}</span>
</div>

<style>
	.cover {
		position: relative;
		display: flex;
		justify-content: center;
		padding: 18px 12px 52px;
		background: var(--c);
		container-type: inline-size;
		box-shadow:
			inset 0 0 0 5px var(--c),
			inset 0 0 0 6px var(--bronze),
			4px 6px 0 var(--line);
		overflow: hidden;
	}
	.title {
		align-self: flex-start;
		max-width: 100%;
		max-height: 100%;
		overflow: hidden;
		padding: 10px 8px;
		border: 1px solid color-mix(in srgb, var(--on-cover) 35%, transparent);
		color: var(--on-cover);
		font-family: var(--font-title);
		font-size: clamp(14px, 13cqi, 22px);
		font-weight: 700;
		line-height: 1.15;
		text-align: center;
		overflow-wrap: anywhere;
	}
	.seal {
		position: absolute;
		right: 14px;
		bottom: 14px;
		display: flex;
		width: 30px;
		height: 30px;
		align-items: center;
		justify-content: center;
		background: var(--cinnabar);
		color: var(--on-cinnabar);
		font-family: var(--font-title);
		font-size: 18px;
		font-weight: 700;
	}
</style>
