// Kiểm tra tương phản WCAG cho cả 4 theme trong src/lib/styles/theme.css.
// Chữ thân bài và mọi cặp chữ/nền dùng cho chữ thường phải đạt ≥ 4.5:1.
import { readFileSync } from 'node:fs';

const css = readFileSync(new URL('../src/lib/styles/theme.css', import.meta.url), 'utf8');
const THEMES = ['light', 'sepia', 'dark', 'bamboo'];
const PAIRS = [
	['ink', 'paper'],
	['ink', 'paper-raised'],
	['ink', 'field'],
	['ink-soft', 'paper'],
	['ink-muted', 'paper'],
	['ink-muted', 'paper-raised'],
	['label', 'paper'],
	['label', 'paper-raised'],
	['cinnabar', 'paper'],
	['cinnabar', 'paper-raised'],
	['on-cinnabar', 'cinnabar'],
	['jade', 'paper-raised'],
	['on-inverse', 'inverse'],
	['ok-fg', 'ok-bg'],
	['edited-fg', 'edited-bg'],
	['warn-fg', 'warn-bg'],
	['danger-fg', 'danger-bg'],
	['info-fg', 'info-bg']
];

function tokens(theme) {
	const re = new RegExp(`\\[data-theme='${theme}'\\]\\s*\\{([^}]*)\\}`);
	const block = css.match(re)?.[1];
	if (!block) throw new Error(`không thấy theme ${theme}`);
	return Object.fromEntries([...block.matchAll(/--([\w-]+):\s*(#[0-9a-f]{6})/gi)].map((m) => [m[1], m[2]]));
}

function luminance(hex) {
	const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
	const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
	return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function ratio(a, b) {
	const [hi, lo] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (hi + 0.05) / (lo + 0.05);
}

let failed = 0;
for (const theme of THEMES) {
	const t = tokens(theme);
	const rows = PAIRS.map(([fg, bg]) => {
		if (!t[fg] || !t[bg]) throw new Error(`${theme}: thiếu --${fg} hoặc --${bg}`);
		const r = ratio(t[fg], t[bg]);
		if (r < 4.5) failed++;
		return `${r < 4.5 ? 'FAIL' : ' ok '} ${r.toFixed(2).padStart(5)}  --${fg} / --${bg}`;
	});
	console.log(`\n[${theme}]\n${rows.join('\n')}`);
}
if (failed) {
	console.error(`\n${failed} cặp màu dưới 4.5:1`);
	process.exit(1);
}
console.log('\nMọi cặp đạt ≥ 4.5:1');
