import { expect, test } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, shot, translateViaApi } from './helpers';

const H = { 'X-Requested-With': 'e2e' };

test('hàng chờ: đồng ý kèm sửa, bỏ qua', async ({ page }, info) => {
	const novel = info.project.name === 'mobile' ? 3 : 2;
	await login(page, `/novels/${novel}/glossary`);
	await expect(page.getByRole('heading', { level: 1 })).toContainText('Bộ tên riêng của truyện này');
	await expect(page.getByRole('heading', { name: 'Tên mới chờ duyệt · 2' })).toBeVisible();
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'main button, main a');
	await shot(page, info, 'glossary');

	await page.getByLabel('Bản dịch đề xuất cho 苏柔').fill('Tô Nhược');
	await page.getByRole('button', { name: 'Đồng ý 苏柔' }).click();
	await expect(page.getByRole('status')).toContainText('Đã thêm "苏柔" → "Tô Nhược"');
	await page.getByRole('button', { name: 'Bỏ qua 青阳镇' }).click();
	await expect(page.getByRole('heading', { name: 'Tên mới chờ duyệt · 0' })).toBeVisible();
	await expect(page.locator('.tablets li')).toHaveCount(1);
	await expect(page.locator('.tablets')).toContainText('Tô Nhược');
	const terms = await (await page.request.get(`/api/novels/${novel}/glossary`)).json();
	expect(terms).toEqual([{ source_term: '苏柔', target_term: 'Tô Nhược', note: 'nhân vật' }]);
});

test('đổi tên: cảnh báo số chương, lan sang chương đã dịch; xoá có xác nhận', async ({ page }, info) => {
	await login(page);
	const text = (n: number) => `第${n}章 标题\n林动 Lâm Động bước lên núi.\nLâm Động Nhuận đứng đó.`;
	const r = await page.request.post('/api/novels', {
		headers: H,
		multipart: { file: { name: `doiten-${info.project.name}.txt`, mimeType: 'text/plain', buffer: Buffer.from(text(1) + '\n' + text(2)) } }
	});
	const id = (await r.json()).id;
	await page.request.put(`/api/novels/${id}/glossary`, { headers: H, data: { source_term: '林动', target_term: 'Lâm Động' } });
	await translateViaApi(page, id, 1);
	await translateViaApi(page, id, 2);
	await page.request.put(`/api/novels/${id}/chapters/2`, { headers: H, data: { translated_text: 'Lâm Động sửa tay.' } });

	await page.goto(`/novels/${id}/glossary`);
	await page.getByRole('button', { name: 'Sửa 林动' }).click();
	await page.getByLabel('Bản dịch').fill('Lâm Đông');
	const impact = page.locator('.impact');
	await expect(impact).toContainText('ảnh hưởng 2 chương');
	await expect(impact).toContainText('1 chương đã dịch');
	await expect(impact).toContainText('1 chương đã biên tập');
	await shot(page, info, 'glossary-rename');
	await page.getByRole('button', { name: 'Lưu thay đổi' }).click();
	await expect(page.getByRole('status').first()).toContainText('Đã đổi "林动" thành "Lâm Đông"');

	const ch1 = await (await page.request.get(`/api/novels/${id}/chapters/1`)).json();
	expect(ch1.translated_text).toContain('Lâm Đông bước lên núi');
	expect(ch1.translated_text).toContain('Lâm Đông Nhuận'); // nguyên từ "Lâm Động" vẫn được thay
	const ch2 = await (await page.request.get(`/api/novels/${id}/chapters/2`)).json();
	expect(ch2.translated_text).toBe('Lâm Động sửa tay.'); // chương đã biên tập giữ nguyên
	expect(ch2.glossary_outdated).toBe(true);

	await page.getByRole('button', { name: 'Xoá 林动' }).click();
	const dialog = page.getByRole('alertdialog');
	await expect(dialog).toContainText('2 chương đã dịch có chứa tên này');
	await dialog.getByRole('button', { name: 'Xoá tên' }).click();
	await expect(page.getByText('Chưa có tên nào.')).toBeVisible();
});
