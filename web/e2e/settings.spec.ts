import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, PASSWORD, shot } from './helpers';

const H = { 'X-Requested-With': 'e2e' };
const DEFAULTS = { theme: 'light', font_size: 18, line_height: 1.8, prefetch: true };

// Tùy chọn là trạng thái dùng chung của cả server: luôn trả về mặc định sau mỗi test.
test.afterEach(async ({ request }) => {
	await request.post('/api/auth/login', { headers: H, data: { password: PASSWORD } });
	await request.patch('/api/preferences', { headers: H, data: DEFAULTS });
});

async function slide(page: Page, label: RegExp, value: number) {
	await page.getByLabel(label).evaluate((el, v) => {
		const input = el as HTMLInputElement;
		input.value = String(v);
		input.dispatchEvent(new Event('input', { bubbles: true }));
		input.dispatchEvent(new Event('change', { bubbles: true }));
	}, value);
}

test('trang cài đặt: giao diện đọc, chuẩn bị trước, bảng lượt dùng, ghi chú dữ liệu', async ({ page }, info) => {
	await login(page, '/settings');
	await expect(page.getByRole('heading', { level: 1 })).toContainText('Cài đặt');
	await expect(page.getByRole('heading', { name: 'Giao diện đọc' })).toBeVisible();
	for (const name of ['Tuyên chỉ', 'Hoàng quyển', 'Dạ nguyệt', 'Trúc lâm']) {
		await expect(page.getByRole('button', { name })).toBeVisible();
	}
	await expect(page.getByRole('button', { name: 'Tuyên chỉ' })).toHaveAttribute('aria-pressed', 'true');

	const rows = page.locator('section.quota tbody tr');
	await expect(rows).toHaveCount(2);
	await expect(rows.nth(0)).toContainText('Bước 1');
	await expect(rows.nth(0).locator('td.num')).toHaveText(/(^|\s)12$/);
	await expect(rows.nth(0)).toContainText('Còn lượt');
	await expect(rows.nth(1)).toContainText(/Hết lượt hôm nay · làm mới lúc \d{2}:\d{2}/);
	await expect(page.getByText(/Đang dùng provider echo/)).toBeVisible(); // server e2e ghi đè provider
	await expect(page.getByText(/gói miễn phí, Google/)).toBeVisible();
	await expect(page.getByRole('switch')).toBeChecked();

	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'nav a, main button, main input[type=range], main label.switch');
	await shot(page, info, 'settings');
});

test('đổi theme, cỡ chữ, giãn dòng: lưu server-side, áp dụng trên trình duyệt khác', async ({ page, browser }, info) => {
	await login(page, '/settings');
	await page.getByRole('button', { name: 'Dạ nguyệt' }).click();
	await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
	await expect(page.getByRole('button', { name: 'Dạ nguyệt' })).toHaveAttribute('aria-pressed', 'true');
	await slide(page, /Cỡ chữ/, 22);
	await expect(page.getByText('Đã lưu cỡ chữ.')).toBeVisible();
	await slide(page, /Giãn dòng/, 2.1);
	await expect(page.getByText('Đã lưu giãn dòng.')).toBeVisible();
	await expect(page.getByLabel('Xem trước')).toHaveCSS('font-size', '22px');
	await shot(page, info, 'settings-dark');

	// Trình duyệt khác (context mới, không có localStorage) nhận cùng tùy chọn từ server.
	const other = await browser.newContext({ viewport: page.viewportSize() ?? undefined });
	const p2 = await other.newPage();
	try {
		await login(p2, '/novels/2/chapters/1');
		await expect(p2.locator('html')).toHaveAttribute('data-theme', 'dark');
		await expect(p2.locator('.para').first()).toBeVisible();
		const style = await p2.evaluate(() => {
			const s = document.documentElement.style;
			return [s.getPropertyValue('--reader-size'), s.getPropertyValue('--reader-leading')];
		});
		expect(style).toEqual(['22px', '2.1']);
		await expect(p2.locator('.para').first()).toHaveCSS('font-size', '22px');
	} finally {
		await other.close();
	}
});

test('công tắc chuẩn bị trước bật/tắt prefetch', async ({ page }) => {
	await login(page, '/settings');
	const sw = page.getByRole('switch');
	await sw.uncheck();
	await expect(page.getByText('Đã lưu tắt chuẩn bị trước.')).toBeVisible();
	await expect(sw).not.toBeChecked();
	expect((await (await page.request.get('/api/settings')).json()).prefetch_enabled).toBe(false);
	await page.reload();
	await expect(page.getByRole('switch')).not.toBeChecked();
	await page.getByRole('switch').check();
	await expect(page.getByText('Đã lưu bật chuẩn bị trước.')).toBeVisible();
	expect((await (await page.request.get('/api/settings')).json()).prefetch_enabled).toBe(true);
});

test('đăng xuất → về trang đăng nhập, session hết hiệu lực', async ({ page }) => {
	await login(page, '/settings');
	await page.getByRole('button', { name: 'Đăng xuất' }).click();
	await page.waitForURL((u) => u.pathname === '/login');
	expect((await page.request.get('/api/auth/me')).status()).toBe(401);
	await page.goto('/settings');
	await page.waitForURL((u) => u.pathname === '/login');
});
