import { expect, test } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, shot, translateViaApi, uploadNovel } from './helpers';

// Test làm thay đổi dữ liệu dùng truyện 2 (truyện 1 giữ nguyên cho test mục lục), mỗi project
// một nhóm chương riêng vì dùng chung một database.
const N = 2;
const CH = (project: string) =>
	project === 'mobile' ? { pending: 2, next: 4, failed: 5 } : { pending: 3, next: 6, failed: 7 };

test('chương đã dịch hiển thị ngay, không gọi dịch; xem bản gốc; nhãn nguồn gốc', async ({ page }, info) => {
	const posts: string[] = [];
	page.on('request', (r) => r.method() === 'POST' && r.url().includes('/translate') && posts.push(r.url()));
	// Truyện 1 là dữ liệu cố định cho test mục lục: không để tín hiệu đọc kích hoạt prefetch.
	await page.route('**/api/novels/1/chapters/*/reading-signal', (r) =>
		r.fulfill({ json: { started: false, reason: 'disabled', chapter_index: null } })
	);
	await login(page, '/novels/1/chapters/2');
	await expect(page.locator('.para').first()).toContainText('[VI]');
	const fallback = page.locator('.notice', { hasText: /Dịch bằng model dự phòng \(bước 2/ });
	await expect(fallback).toBeVisible();
	await expect(fallback.getByRole('button', { name: 'Dịch lại' })).toBeVisible();
	expect(posts).toEqual([]);
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'header button, header a, footer a, footer button');
	await shot(page, info, 'reader-fallback');

	await page.getByRole('button', { name: 'Xem bản gốc' }).click();
	await expect(page.locator('.para').first()).toContainText('林动站在山上');
	await page.getByRole('button', { name: 'Xem bản dịch' }).click();
	await expect(page.locator('.para').first()).toContainText('[VI]');

	await page.goto('/novels/1/chapters/3');
	await expect(page.getByText('Đã biên tập tay.')).toBeVisible();
	await expect(page.getByText('Bộ tên đã đổi sau khi dịch chương này.')).toBeVisible();
	await page.goto('/novels/1/chapters/4');
	await expect(page.getByText('Có thể thiếu đoạn so với bản gốc.')).toBeVisible();
});

test('chương chưa dịch: tự dịch, các đoạn hiện dần', async ({ page }, info) => {
	const { pending } = CH(info.project.name);
	await login(page, `/novels/${N}/chapters/${pending}`);
	const status = page.getByRole('status');
	await expect(status).toContainText('Đang dịch');
	// đoạn đầu tiên xuất hiện khi việc dịch còn đang chạy
	await expect(page.locator('.para').first()).toBeVisible();
	await expect(status).toBeVisible();
	const midway = await page.locator('.para').count();
	expect(midway).toBeLessThan(8);
	await shot(page, info, 'reader-streaming');
	await expect(status).toHaveCount(0, { timeout: 15_000 });
	await expect(page.locator('.para')).toHaveCount(8);
	await expect(page.getByRole('heading', { level: 1 })).toContainText('[VI]');
});

test('gắn vào bản dịch đang chạy (prefetch), không tạo job thứ hai', async ({ page }, info) => {
	const { next } = CH(info.project.name);
	await login(page, `/novels/${N}`);
	const r = await page.request.post(`/api/novels/${N}/chapters/${next - 1}/reading-signal`, {
		data: { signal: 'explicit' },
		headers: { 'X-Requested-With': 'e2e' }
	});
	expect((await r.json()).reason).toMatch(/started|already_translated|in_progress/);
	const posts: string[] = [];
	page.on('request', (q) => q.method() === 'POST' && q.url().includes('/translate') && posts.push(q.url()));
	await page.goto(`/novels/${N}/chapters/${next}`);
	await expect(page.locator('.para')).toHaveCount(8, { timeout: 15_000 });
	expect(posts).toEqual([]);
});

test('chương lỗi: báo lý do, thử lại thì dịch được', async ({ page }, info) => {
	const { failed } = CH(info.project.name);
	await login(page, `/novels/${N}/chapters/${failed}`);
	const alert = page.getByRole('alert');
	await expect(alert).toContainText('Dịch lỗi');
	await expect(alert.getByRole('button', { name: 'Xem bản gốc' })).toBeVisible();
	await shot(page, info, 'reader-failed');
	await alert.getByRole('button', { name: 'Thử lại' }).click();
	await expect(page.locator('.para')).toHaveCount(8, { timeout: 15_000 });
});

test('hết quota: báo giờ làm mới, không đánh dấu lỗi', async ({ page }, info) => {
	await login(page, '/novels/3');
	await page.route('**/api/novels/3/chapters/1/translate', (route) =>
		route.fulfill({
			status: 429,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'Hết quota', category: 'daily_quota', reset_at: '2030-01-01T08:00:00Z' })
		})
	);
	await page.goto('/novels/3/chapters/1');
	const alert = page.getByRole('alert');
	await expect(alert).toContainText('Hết lượt dịch hôm nay');
	await expect(alert).toContainText('2030');
	await expect(alert).toContainText('trạng thái Chưa dịch');
	await shot(page, info, 'reader-quota');
	const ch = await (await page.request.get('/api/novels/3/chapters/1')).json();
	expect(ch.status).toBe('pending');
});

test('lỗi provider khi gửi yêu cầu (502) hiện lý do', async ({ page }) => {
	await login(page, '/novels/3');
	await page.route('**/api/novels/3/chapters/2/translate', (route) =>
		route.fulfill({
			status: 502,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'Thiếu GEMINI_API_KEY', category: 'config' })
		})
	);
	await page.goto('/novels/3/chapters/2');
	await expect(page.getByRole('alert')).toContainText('Cấu hình model chưa đúng: Thiếu GEMINI_API_KEY');
});

test('chuyển chương; chương cuối thì nút sau bị tắt; tùy chọn đọc lưu server', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `chuyen-${info.project.name}`, 3, 2);
	await translateViaApi(page, id, 1);
	await page.goto(`/novels/${id}/chapters/1`);
	await expect(page.getByRole('button', { name: '‹ Chương trước' })).toBeDisabled();
	await page.getByRole('link', { name: 'Chương 2 ›' }).click();
	await expect(page).toHaveURL(/chapters\/2$/);
	await page.goto(`/novels/${id}/chapters/3`);
	await expect(page.getByRole('button', { name: 'Hết chương' })).toBeDisabled();

	await page.goto(`/novels/${id}/chapters/1`);
	await page.getByRole('button', { name: 'Giao diện đọc' }).click();
	const panel = page.getByRole('dialog', { name: 'Giao diện đọc' });
	await panel.getByRole('button', { name: /Dạ nguyệt/ }).click();
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
	await panel.getByRole('button', { name: 'Tăng cỡ chữ' }).click();
	await expectNoHorizontalScroll(page);
	await shot(page, info, 'reader-dark-panel');
	const prefs = await (await page.request.get('/api/preferences')).json();
	expect(prefs.theme).toBe('dark');
	await page.request.patch('/api/preferences', {
		data: { theme: 'light', font_size: 18 },
		headers: { 'X-Requested-With': 'e2e' }
	});
});
