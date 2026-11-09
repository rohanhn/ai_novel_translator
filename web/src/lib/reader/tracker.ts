// Theo dõi việc đọc một chương (spec translation-prefetch, web-reader):
// - Tín hiệu đọc: chương hiển thị đủ 30 giây (không tính lúc tab ẩn), hoặc cuộn quá 60%.
//   Mỗi chương gửi tối đa một lần; nút "Chuẩn bị chương tiếp" gửi tín hiệu `explicit`.
// - Tiến độ: lưu sau 5 giây không cuộn; khi rời trang (pagehide) gửi ngay bằng fetch keepalive
//   (sendBeacon không gửi được header chống CSRF).
import { CSRF_HEADER, post } from '../api.js';

export const VISIBLE_MS = 30_000;
export const SCROLL_RATIO = 0.6;
export const SAVE_DEBOUNCE_MS = 5_000;

export type Decision = { started: boolean; reason: string; chapter_index: number | null };

export function scrollRatio(): number {
	const max = document.documentElement.scrollHeight - window.innerHeight;
	return max <= 0 ? 1 : Math.min(1, Math.max(0, window.scrollY / max));
}

export function scrollToRatio(ratio: number): void {
	const max = document.documentElement.scrollHeight - window.innerHeight;
	if (max > 0) window.scrollTo(0, Math.round(ratio * max));
}

export class ChapterTracker {
	private signalled = false;
	private visibleMs = 0;
	private lastTick = 0;
	private tick: ReturnType<typeof setInterval> | null = null;
	private saveTimer: ReturnType<typeof setTimeout> | null = null;
	private dirty = false;
	private readonly onScroll = () => this.scrolled();
	private readonly onVisibility = () => this.visibility();
	private readonly onHide = () => this.flush(true);

	constructor(
		private novelId: number,
		private index: number,
		private onDecision: (d: Decision) => void
	) {}

	start(): void {
		this.lastTick = performance.now();
		this.tick = setInterval(() => this.count(), 1000);
		window.addEventListener('scroll', this.onScroll, { passive: true });
		document.addEventListener('visibilitychange', this.onVisibility);
		window.addEventListener('pagehide', this.onHide);
	}

	stop(): void {
		if (this.tick) clearInterval(this.tick);
		this.tick = null;
		window.removeEventListener('scroll', this.onScroll);
		document.removeEventListener('visibilitychange', this.onVisibility);
		window.removeEventListener('pagehide', this.onHide);
		this.flush(true);
	}

	/** Bấm "Chuẩn bị chương tiếp". */
	async explicit(): Promise<Decision> {
		return this.send('explicit', true);
	}

	private count(): void {
		const now = performance.now();
		if (document.visibilityState === 'visible') this.visibleMs += now - this.lastTick;
		this.lastTick = now;
		if (this.visibleMs >= VISIBLE_MS) this.send('visible_30s');
	}

	private visibility(): void {
		this.lastTick = performance.now(); // không cộng khoảng thời gian tab bị ẩn
		if (document.visibilityState === 'hidden') this.flush(true);
	}

	private scrolled(): void {
		if (scrollRatio() >= SCROLL_RATIO) this.send('scrolled_60');
		this.dirty = true;
		if (this.saveTimer) clearTimeout(this.saveTimer);
		this.saveTimer = setTimeout(() => this.flush(false), SAVE_DEBOUNCE_MS);
	}

	private async send(signal: string, force = false): Promise<Decision> {
		if (this.signalled && !force) return { started: false, reason: 'sent', chapter_index: null };
		this.signalled = true;
		const d = await post<Decision>(`/api/novels/${this.novelId}/chapters/${this.index}/reading-signal`, { signal });
		this.onDecision(d);
		return d;
	}

	/** Lưu tiến độ ngay (keepalive: vẫn gửi khi trang đang đóng). */
	flush(keepalive: boolean): void {
		if (this.saveTimer) clearTimeout(this.saveTimer);
		this.saveTimer = null;
		if (!this.dirty) return;
		this.dirty = false;
		saveProgress(this.novelId, this.index, scrollRatio(), keepalive);
	}
}

export function saveProgress(novelId: number, index: number, position: number, keepalive = false): void {
	fetch(`/api/novels/${novelId}/progress`, {
		method: 'PUT',
		keepalive,
		credentials: 'same-origin',
		headers: { 'Content-Type': 'application/json', [CSRF_HEADER]: 'fetch' },
		body: JSON.stringify({ chapter_index: index, position: Math.round(position * 1000) / 1000 })
	}).catch(() => {});
}

/** Rời truyện: huỷ prefetch chưa gửi request. */
export function leaveNovel(novelId: number): void {
	fetch(`/api/novels/${novelId}/leave`, {
		method: 'POST',
		keepalive: true,
		credentials: 'same-origin',
		headers: { [CSRF_HEADER]: 'fetch' }
	}).catch(() => {});
}

export function decisionText(d: Decision): string {
	const n = d.chapter_index;
	switch (d.reason) {
		case 'started':
			return `Đang chuẩn bị trước chương ${n}.`;
		case 'already_translated':
			return `Chương ${n} đã dịch sẵn.`;
		case 'in_progress':
			return `Chương ${n} đang được dịch.`;
		case 'edited':
			return `Chương ${n} đã biên tập tay, không dịch lại tự động.`;
		case 'no_next_chapter':
			return 'Đây là chương cuối.';
		case 'disabled':
			return 'Dịch trước đang tắt trong Cài đặt.';
		case 'primary_exhausted':
			return 'Model chính đã hết lượt hôm nay nên tạm không dịch trước.';
		default:
			return '';
	}
}
