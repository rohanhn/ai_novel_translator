import { writeFileSync } from 'node:fs';
import { expect, test } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, PASSWORD, setProgress, shot } from './helpers';

test('chưa đăng nhập → chuyển sang /login, sai mật khẩu báo lỗi, đúng thì quay lại', async ({ page }, info) => {
	await page.goto('/novels/1');
	await page.waitForURL(/\/login\?next=%2Fnovels%2F1/);
	await expectNoHorizontalScroll(page);
	await page.getByLabel('Mật khẩu').fill('sai-roi');
	await page.getByRole('button', { name: 'Đăng nhập' }).click();
	await expect(page.getByRole('alert')).toHaveText('Sai mật khẩu.');
	await shot(page, info, 'login-error');
	await page.getByLabel('Mật khẩu').fill(PASSWORD);
	await page.getByRole('button', { name: 'Đăng nhập' }).click();
	await page.waitForURL((u) => u.pathname === '/novels/1');
});

test('thư viện: đọc gần nhất lên đầu, nhãn rõ nghĩa, bố cục', async ({ page }, info) => {
	await login(page);
	// test khác có thể đã đọc truyện khác: đặt lại "đọc gần nhất"
	await setProgress(page, 2, 1, 0.5);
	await setProgress(page, 1, 4, 0.62);
	await page.reload();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText('vu-dong-can-khon');
	await expect(page.getByText('Đang ở Chương 4')).toBeVisible();
	await expect(page.getByText('đã đọc 62%')).toBeVisible();
	await expect(page.getByText('2 tên mới chờ duyệt')).toBeVisible();
	await page.getByRole('searchbox').fill('-');
	const titles = await page.locator('.card-title').allTextContents();
	expect(titles.slice(0, 2)).toEqual(['vu-dong-can-khon', 'pham-nhan-tu-tien']);
	// nhãn tu tiên luôn kèm nhãn rõ nghĩa
	await expect(page.getByRole('link', { name: /Tàng Thư Các\s*Thư viện/ })).toBeVisible();
	await expect(page.getByRole('link', { name: /Thiết Lập\s*Cài đặt/ })).toBeVisible();
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page);
	await page.getByRole('searchbox').fill('');
	await shot(page, info, 'library');
	await page.getByRole('searchbox').fill('gia');
	await expect(page.locator('.card-title')).toHaveText(['gia-thien']);
});

test('upload: báo lỗi file quá 50 MB, upload thành công rồi xoá có xác nhận', async ({ page }, info) => {
	await login(page);
	await page.getByRole('button', { name: 'Upload .txt' }).click();
	const dialog = page.getByRole('dialog');
	const big = info.outputPath('toan-tap.txt');
	writeFileSync(big, Buffer.alloc(50 * 1024 * 1024 + 1, 0x41));
	await dialog.locator('input[type=file]').setInputFiles(big);
	await expect(dialog.getByRole('alert')).toContainText('File quá lớn');
	await expect(dialog.getByRole('button', { name: 'Upload' })).toBeDisabled();
	await expectNoHorizontalScroll(page);
	await shot(page, info, 'upload-too-large');

	const name = `e2e-${info.project.name}`;
	await dialog.locator('input[type=file]').setInputFiles({
		name: `${name}.txt`,
		mimeType: 'text/plain',
		buffer: Buffer.from('第1章 开始\n林动。\n第2章 继续\n修炼。\n')
	});
	await expect(dialog.getByPlaceholder(name)).toBeVisible(); // tên mặc định = tên file
	await dialog.getByRole('button', { name: 'Upload' }).click();
	await page.waitForURL(/\/novels\/\d+$/);

	await page.goto('/');
	const card = page.locator('.card', { hasText: name });
	await card.getByRole('button', { name: /Xoá/ }).click();
	const confirm = page.getByRole('alertdialog');
	await expect(confirm).toContainText(`Xoá "${name}"?`);
	await expect(confirm).toContainText('Không thể hoàn tác');
	await shot(page, info, 'delete-confirm');
	await confirm.getByRole('button', { name: 'Giữ lại' }).click();
	await expect(card).toBeVisible();
	await card.getByRole('button', { name: /Xoá/ }).click();
	await page.getByRole('alertdialog').getByRole('button', { name: 'Xoá truyện' }).click();
	await expect(card).toHaveCount(0);
});
