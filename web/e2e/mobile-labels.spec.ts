// Task 9.10: kiểm tra mobile-first và nhãn trên mọi trang (spec web-reader "Mobile-first" và
// "Plain-language labels"). Chạy ở cả 360px (mobile) và 1280px (desktop).
import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login } from './helpers';

const PAGES = [
	{ path: '/', ready: 'h2:has-text("Kho truyện")' },
	{ path: '/novels/1', ready: '#toc-h' },
	{ path: '/novels/1/chapters/1', ready: '.para' },
	{ path: '/novels/1/glossary', ready: '#list-h' },
	{ path: '/settings', ready: 'section.quota tbody tr' }
];

// Mọi thứ bấm được trên trang (trừ link nằm trong đoạn văn).
const TARGETS = 'header a, header button, nav a, main button, main a.btn, footer a, footer button, input[type=range], label.switch';

/** Nhãn kiểu tu tiên (.xianxia) phải có chữ thường đi kèm trong cùng phần tử cha; chữ Hán
 *  trang trí (.han) phải ẩn với trình đọc màn hình hoặc nằm trên phần tử có aria-label. */
async function expectPlainLabels(page: Page) {
	const problems = await page.evaluate(() => {
		const out: string[] = [];
		const visible = (el: Element) => (el as HTMLElement).offsetParent !== null || el.closest('dialog[open]');
		for (const el of document.querySelectorAll('.xianxia')) {
			if (!visible(el)) continue;
			const parent = el.parentElement!;
			const rest = (parent.textContent ?? '').replace(el.textContent ?? '', '').trim();
			if (!rest) out.push(`".xianxia" thiếu nhãn thường: ${el.textContent}`);
		}
		for (const el of document.querySelectorAll('.han')) {
			if (!visible(el)) continue;
			const hidden = el.closest('[aria-hidden="true"]');
			const labelled = el.closest('[aria-label]');
			if (!hidden && !labelled) out.push(`chữ Hán không có nhãn: ${el.textContent}`);
		}
		return out;
	});
	expect(problems).toEqual([]);
}

test('đăng nhập: không cuộn ngang, vùng chạm ≥44px', async ({ page }) => {
	await page.goto('/login');
	await expect(page.getByLabel('Mật khẩu')).toBeVisible();
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'main button, main input');
	await expectPlainLabels(page);
});

for (const p of PAGES) {
	test(`${p.path}: không cuộn ngang, vùng chạm ≥44px, nhãn tu tiên có nhãn thường`, async ({ page }) => {
		// Chỉ xem, không ghi vào dữ liệu dùng chung: chặn tín hiệu đọc (sẽ kích hoạt dịch trước)
		// và việc lưu tiến độ (sẽ đổi "Đọc tiếp" mà test khác kiểm tra).
		await page.route('**/reading-signal', (r) => r.fulfill({ status: 200, json: { started: false, reason: 'disabled' } }));
		await page.route('**/progress', (r) =>
			r.request().method() === 'PUT' ? r.fulfill({ status: 204 }) : r.fallback()
		);
		await page.route('**/leave', (r) => r.fulfill({ status: 204 }));
		await login(page, p.path);
		await expect(page.locator(p.ready).first()).toBeVisible();
		await expectNoHorizontalScroll(page);
		await expectTouchTargets(page, TARGETS);
		await expectPlainLabels(page);
		// Rời trang khi route chặn vẫn còn hiệu lực (lượt lưu tiến độ lúc pagehide cũng bị chặn).
		await page.goto('about:blank');
	});
}

test('điều hướng chính: mỗi mục tu tiên kèm nhãn thường, vùng chạm ≥44px', async ({ page }) => {
	await login(page, '/');
	const nav = page.getByRole('navigation', { name: 'Chính' });
	await expect(nav.getByRole('link', { name: /Tàng Thư Các\s*Thư viện/ })).toBeVisible();
	await expect(nav.getByRole('link', { name: /Thiết Lập\s*Cài đặt/ })).toBeVisible();
	for (const link of await nav.getByRole('link').all()) {
		const box = (await link.boundingBox())!;
		expect(box.height).toBeGreaterThanOrEqual(44);
		expect(box.width).toBeGreaterThanOrEqual(44);
	}
	// Pill quota: chữ thường luôn hiện; "Pháp khí" chỉ là tiền tố trang trí (ẩn trên màn hẹp).
	await expect(page.locator('a.pill')).toContainText(/(còn|hết) lượt hôm nay/);
});

test('trạng thái chương dùng lời thường (Lỗi kèm lý do), không dùng thuật ngữ tu tiên', async ({ page }) => {
	await login(page, '/novels/1');
	await expect(page.locator('#toc-h')).toBeVisible();
	const chips = await page.locator('.chip').allInnerTexts();
	expect(chips.length).toBeGreaterThan(0);
	const themed = /Tu vi|Cảnh giới|Luyện Khí|Trúc Cơ|Kim Đan|Nguyên Anh|Hóa Thần|Đại Thừa|Pháp khí|Danh Lục/;
	expect(chips.filter((t) => themed.test(t))).toEqual([]);
	await expect(page.locator('.chip', { hasText: 'Lỗi' }).first()).toBeVisible();
});
