import { expect, type Page, type TestInfo } from '@playwright/test';

export const PASSWORD = 'e2e-mat-khau';

export async function login(page: Page, next = '/') {
	await page.goto(`/login?next=${encodeURIComponent(next)}`);
	await page.getByLabel('Mật khẩu').fill(PASSWORD);
	await page.getByRole('button', { name: 'Đăng nhập' }).click();
	await page.waitForURL((u) => u.pathname === next);
}

/** Không có thanh cuộn ngang (spec: mobile-first, 360px). */
export async function expectNoHorizontalScroll(page: Page) {
	const { scroll, width } = await page.evaluate(() => ({
		scroll: document.documentElement.scrollWidth,
		width: window.innerWidth
	}));
	expect(scroll, 'trang rộng hơn viewport').toBeLessThanOrEqual(width);
}

/** Mọi phần tử bấm được trong vùng chọn có chiều cao/rộng ≥ 44px. */
export async function expectTouchTargets(page: Page, selector = 'nav a, main button, main a.btn') {
	const small = await page.$$eval(selector, (els) =>
		els
			.filter((el) => (el as HTMLElement).offsetParent !== null)
			.map((el) => ({ el: el as HTMLElement, r: el.getBoundingClientRect() }))
			.filter(({ r }) => r.height < 44 || r.width < 44)
			.map(({ el, r }) => `${el.tagName} "${el.textContent?.trim().slice(0, 30)}" ${Math.round(r.width)}x${Math.round(r.height)}`)
	);
	expect(small, 'vùng chạm < 44px').toEqual([]);
}

export async function shot(page: Page, info: TestInfo, name: string) {
	await page.screenshot({ path: `e2e/screenshots/${info.project.name}-${name}.png`, fullPage: true });
}

const H = { 'X-Requested-With': 'e2e' };

/** Tạo truyện riêng cho một test (tách dữ liệu giữa các test/project). */
export async function uploadNovel(page: Page, name: string, chapters: number, paragraphs = 8): Promise<number> {
	const para = '林动站在山上，看着远方的青阳镇，心中暗暗发誓一定要变强。';
	const text = Array.from({ length: chapters }, (_, i) =>
		`第${i + 1}章 标题${i + 1}\n` + Array.from({ length: paragraphs }, (_, k) => `${k + 1}. ${para}`).join('\n')
	).join('\n');
	const r = await page.request.post('/api/novels', {
		headers: H,
		multipart: { file: { name: `${name}.txt`, mimeType: 'text/plain', buffer: Buffer.from(text) } }
	});
	expect(r.status()).toBe(201);
	return (await r.json()).id;
}

/** Dịch chương qua API và chờ xong. */
export async function translateViaApi(page: Page, novelId: number, index: number) {
	await page.request.post(`/api/novels/${novelId}/chapters/${index}/translate`, { headers: H, data: {} });
	await waitStatus(page, novelId, index, 'translated');
}

export async function waitStatus(page: Page, novelId: number, index: number, status: string) {
	await expect
		.poll(async () => (await (await page.request.get(`/api/novels/${novelId}/chapters/${index}`)).json()).status, {
			timeout: 20_000
		})
		.toBe(status);
}

export async function setProgress(page: Page, novelId: number, index: number, position: number) {
	await page.request.put(`/api/novels/${novelId}/progress`, {
		headers: H,
		data: { chapter_index: index, position }
	});
}

/** Vị trí đọc đã lưu (0 nếu chưa có; API trả 204 khi chưa đọc). */
export async function savedPosition(page: Page, novelId: number): Promise<number> {
	const r = await page.request.get(`/api/novels/${novelId}/progress`);
	return r.status() === 200 ? (await r.json()).position : 0;
}
