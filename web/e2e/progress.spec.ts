import { expect, test, type Page } from '@playwright/test';
import { login, translateViaApi, uploadNovel, waitStatus } from './helpers';

const signals = (page: Page) => {
	const sent: string[] = [];
	page.on('request', (r) => {
		if (r.url().includes('/reading-signal')) sent.push(JSON.parse(r.postData() ?? '{}').signal);
	});
	return sent;
};

async function setVisibility(page: Page, state: 'visible' | 'hidden') {
	await page.evaluate((s) => {
		Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => s });
		document.dispatchEvent(new Event('visibilitychange'));
	}, state);
}

test('đọc đủ 30 giây (không tính lúc tab ẩn) → chương sau được dịch trước', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `doc30-${info.project.name}`, 3);
	await translateViaApi(page, id, 1);
	const sent = signals(page);
	await page.clock.install();
	await page.goto(`/novels/${id}/chapters/1`);
	await expect(page.locator('.para').first()).toBeVisible();

	await setVisibility(page, 'hidden');
	await page.clock.runFor(45_000);
	expect(sent).toEqual([]); // tab ẩn không được tính

	await setVisibility(page, 'visible');
	await page.clock.runFor(20_000);
	expect(sent).toEqual([]);
	await page.clock.runFor(11_000);
	await expect.poll(() => sent).toEqual(['visible_30s']);
	await expect(page.getByRole('status')).toHaveText('Đang chuẩn bị trước chương 2.');
	await waitStatus(page, id, 2, 'translated');

	await page.clock.runFor(60_000);
	expect(sent).toEqual(['visible_30s']); // mỗi chương chỉ gửi một lần
});

test('cuộn quá 60% → tín hiệu; tiến độ lưu sau 5 giây và khôi phục khi mở lại', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `cuon-${info.project.name}`, 2, 60);
	await translateViaApi(page, id, 1);
	const sent = signals(page);
	await page.clock.install();
	await page.goto(`/novels/${id}/chapters/1`);
	await expect(page.locator('.para').nth(59)).toBeAttached();

	await page.evaluate(() => window.scrollTo(0, (document.documentElement.scrollHeight - innerHeight) * 0.3));
	await page.clock.runFor(1000);
	expect(sent).toEqual([]);
	await page.evaluate(() => window.scrollTo(0, (document.documentElement.scrollHeight - innerHeight) * 0.7));
	await expect.poll(() => sent).toEqual(['scrolled_60']);

	await page.clock.runFor(5_500);
	await expect
		.poll(async () => (await (await page.request.get(`/api/novels/${id}/progress`)).json())?.position ?? 0)
		.toBeGreaterThan(0.6);

	await page.goto(`/novels/${id}`);
	await page.getByRole('link', { name: /Đọc tiếp · Chương 1/ }).click();
	await expect(page.locator('.para').first()).toBeVisible();
	await expect
		.poll(() => page.evaluate(() => scrollY / (document.documentElement.scrollHeight - innerHeight)))
		.toBeGreaterThan(0.6);
});

test('rời trang trước 5 giây vẫn lưu tiến độ (pagehide)', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `roi-${info.project.name}`, 1, 60);
	await translateViaApi(page, id, 1);
	await page.goto(`/novels/${id}/chapters/1`);
	await expect(page.locator('.para').nth(59)).toBeAttached();
	await page.evaluate(() => window.scrollTo(0, (document.documentElement.scrollHeight - innerHeight) * 0.4));
	await page.waitForTimeout(200);
	await page.goto('about:blank');
	await expect
		.poll(async () => (await (await page.request.get(`/api/novels/${id}/progress`)).json())?.position ?? 0)
		.toBeGreaterThan(0.3);
});

test('nút "Chuẩn bị chương tiếp"', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `nut-${info.project.name}`, 2);
	await translateViaApi(page, id, 1);
	await page.goto(`/novels/${id}/chapters/1`);
	await page.getByRole('button', { name: 'Chuẩn bị chương tiếp' }).click();
	await expect(page.getByRole('status')).toHaveText('Đang chuẩn bị trước chương 2.');
	await waitStatus(page, id, 2, 'translated');
});
