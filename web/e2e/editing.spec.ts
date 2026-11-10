import { expect, test } from '@playwright/test';
import { expectNoHorizontalScroll, login, shot, translateViaApi, uploadNovel, waitStatus } from './helpers';

test('biên tập: sửa, lưu → Đã biên tập; dịch lại cần xác nhận', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `bientap-${info.project.name}`, 1, 4);
	await translateViaApi(page, id, 1);
	await page.goto(`/novels/${id}/chapters/1`);
	await page.getByRole('button', { name: 'Biên tập bản dịch' }).click();

	const form = page.getByRole('form', { name: 'Biên tập chương' });
	await expect(form.getByRole('status')).toHaveText('Không có thay đổi');
	await expect(form.getByRole('button', { name: 'Lưu bản sửa' })).toBeDisabled();
	await form.getByLabel('Tiêu đề').fill('Thiếu niên');
	await form.getByLabel('Nội dung').fill('Đoạn một đã sửa.\nĐoạn hai đã sửa.');
	await expect(form.getByRole('status')).toHaveText('Chưa lưu thay đổi');
	await expectNoHorizontalScroll(page);
	await shot(page, info, 'editor');
	await form.getByRole('button', { name: 'Lưu bản sửa' }).click();

	await expect(page.getByRole('heading', { level: 1 })).toHaveText('Thiếu niên');
	await expect(page.locator('.para')).toHaveText(['Đoạn một đã sửa.', 'Đoạn hai đã sửa.']);
	await expect(page.getByText('Đã biên tập tay.')).toBeVisible();
	const saved = await (await page.request.get(`/api/novels/${id}/chapters/1`)).json();
	expect(saved.status).toBe('edited');

	// dịch lại chương đã sửa: hỏi xác nhận, "Giữ bản sửa" thì không đổi gì
	await page.getByRole('button', { name: 'Dịch lại chương' }).click();
	const dialog = page.getByRole('alertdialog');
	await expect(dialog).toContainText('Dịch lại chương đã biên tập?');
	await dialog.getByRole('button', { name: 'Giữ bản sửa' }).click();
	await expect(page.locator('.para')).toHaveText(['Đoạn một đã sửa.', 'Đoạn hai đã sửa.']);

	await page.getByRole('button', { name: 'Dịch lại chương' }).click();
	await page.getByRole('alertdialog').getByRole('button', { name: 'Dịch lại' }).click();
	await waitStatus(page, id, 1, 'translated');
	await expect(page.locator('.para')).toHaveCount(4, { timeout: 15_000 });
});

test('biên tập: không lưu nội dung trống; huỷ thì giữ bản cũ', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `huy-${info.project.name}`, 1, 2);
	await translateViaApi(page, id, 1);
	await page.goto(`/novels/${id}/chapters/1`);
	await page.getByRole('button', { name: 'Biên tập bản dịch' }).click();
	const form = page.getByRole('form', { name: 'Biên tập chương' });
	await form.getByLabel('Nội dung').fill('   ');
	await expect(form.getByRole('button', { name: 'Lưu bản sửa' })).toBeDisabled();
	await form.getByLabel('Nội dung').fill('tạm');
	page.once('dialog', (d) => d.accept());
	await form.getByRole('button', { name: 'Huỷ' }).click();
	await expect(page.locator('.para').first()).toContainText('[VI]');
});
