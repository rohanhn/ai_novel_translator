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
