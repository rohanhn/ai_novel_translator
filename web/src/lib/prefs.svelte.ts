// Tùy chọn đọc (lưu server-side, dùng chung mọi thiết bị). Bản sao trong localStorage chỉ để
// áp theme ngay khi tải trang, tránh nháy màu.
import { get, patch } from './api.js';

export type Theme = 'light' | 'sepia' | 'dark' | 'bamboo';
export type Preferences = {
	theme: Theme;
	font_size: number;
	line_height: number;
	prefetch: boolean;
};

export const THEME_NAMES: Record<Theme, string> = {
	light: 'Tuyên chỉ',
	sepia: 'Hoàng quyển',
	dark: 'Dạ nguyệt',
	bamboo: 'Trúc lâm'
};

const DEFAULTS: Preferences = { theme: 'light', font_size: 18, line_height: 1.8, prefetch: true };
const CACHE_KEY = 'nt-prefs';

function cached(): Preferences {
	try {
		const raw = localStorage.getItem(CACHE_KEY);
		return raw ? { ...DEFAULTS, ...JSON.parse(raw) } : DEFAULTS;
	} catch {
		return DEFAULTS;
	}
}

export const prefs = $state<{ value: Preferences; loaded: boolean }>({
	value: cached(),
	loaded: false
});

export function applyPrefs(p: Preferences): void {
	const root = document.documentElement;
	root.dataset.theme = p.theme;
	root.style.setProperty('--reader-size', `${p.font_size}px`);
	root.style.setProperty('--reader-leading', String(p.line_height));
	try {
		localStorage.setItem(CACHE_KEY, JSON.stringify(p));
	} catch {
		/* chế độ riêng tư: bỏ qua */
	}
}

export async function loadPrefs(): Promise<void> {
	prefs.value = await get<Preferences>('/api/preferences');
	prefs.loaded = true;
	applyPrefs(prefs.value);
}

export async function savePrefs(changes: Partial<Preferences>): Promise<void> {
	prefs.value = await patch<Preferences>('/api/preferences', changes);
	applyPrefs(prefs.value);
}
