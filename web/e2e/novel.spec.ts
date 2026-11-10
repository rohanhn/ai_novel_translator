import { expect, test } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, shot } from './helpers';

test('mục lục: nhãn trạng thái bằng chữ thường, lọc, đọc tiếp', async ({ page }, info) => {
	await login(page, '/novels/1');
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('vu-dong-can-khon');
	await expect(page.getByRole('link', { name: 'Đọc tiếp · Chương 4' })).toHaveAttribute('href', '/novels/1/chapters/4');
	await expect(page.getByRole('link', { name: /Danh Lục · Bộ tên/ })).toContainText('2');

	const row = (n: number) => page.locator('.row').nth(n - 1);
	await expect(row(1).locator('.chips')).toHaveText('Đã dịch');
	await expect(row(2).locator('.chips')).toContainText('Model dự phòng');
	await expect(row(3).locator('.chips')).toContainText('Đã biên tập');
	await expect(row(3).locator('.chips')).toContainText('Bộ tên đã đổi');
	await expect(row(4).locator('.chips')).toContainText('Có thể thiếu đoạn');
	await expect(row(5).locator('.chips')).toHaveText('Lỗi');
	await expect(row(5).getByRole('link')).toContainText('Thử lại');
	await expect(row(6).locator('.chips')).toHaveText('Chưa dịch');
	await expect(row(4).getByRole('link')).toContainText('Đọc tiếp');
	await expect(row(12).locator('.han')).toHaveText('十二');

	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page);
	await shot(page, info, 'novel');

	await page.getByRole('button', { name: 'Cần xem lại · 3' }).click();
	await expect(page.locator('.row')).toHaveCount(3);
	await page.getByRole('button', { name: 'Lỗi · 1' }).click();
	await expect(page.locator('.row')).toHaveCount(1);
	await page.getByRole('button', { name: 'Đã dịch · 4' }).click();
	await expect(page.locator('.row')).toHaveCount(4);
});

test('truyện không tồn tại', async ({ page }) => {
	await login(page, '/novels/999');
	await expect(page.getByRole('alert')).toContainText('Không tìm thấy truyện');
});
