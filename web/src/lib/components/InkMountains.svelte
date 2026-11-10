<script lang="ts">
	// Núi thủy mặc: chỉ trang trí, không nhận chuột, ẩn với trình đọc màn hình.
	let {
		position = 'bottom',
		height = 260,
		sun = false
	}: { position?: 'top' | 'bottom'; height?: number; sun?: boolean } = $props();
</script>

<svg
	class="mountains {position}"
	aria-hidden="true"
	viewBox="0 0 1440 360"
	preserveAspectRatio="none"
	style:height="{height}px"
>
	<path
		d="M0 240 L140 140 L260 210 L400 80 L540 200 L680 120 L820 230 L960 110 L1100 190 L1240 90 L1440 200 L1440 360 L0 360 Z"
		fill="var(--ink)"
		opacity="0.06"
	/>
	<path
		d="M0 300 L180 230 L320 280 L480 200 L640 290 L800 220 L980 290 L1140 210 L1300 270 L1440 230 L1440 360 L0 360 Z"
		fill="var(--jade)"
		opacity="0.08"
	/>
	{#if sun}<circle cx="1180" cy="90" r="40" fill="var(--cinnabar)" opacity="0.1" />{/if}
</svg>

<style>
	.mountains {
		position: absolute;
		left: 0;
		width: 100%;
		pointer-events: none;
		z-index: 0;
	}
	.bottom {
		bottom: 0;
	}
	.top {
		top: 0;
	}
</style>
