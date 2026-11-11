import { expect, test } from '@playwright/test';
import {
	expectNoHorizontalScroll,
	expectTouchTargets,
	login,
	shot,
	translateViaApi,
	uploadNovel
} from './helpers';

// Chữ Hán còn sót trong bản dịch (change flag-untranslated-han; spec web-reader "Untranslated
// text label", "Highlight untranslated characters"). Provider echo trả lại nguyên chữ Hán.

const H = { 'X-Requested-With': 'e2e' };

test('chương còn chữ Hán: nhãn, thông báo, tô sáng; sửa sạch thì mất', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `hansot-${info.project.name}`, 2, 3, true);
	// Bản dịch có đúng 3 chữ Hán còn sót (蕩, 幽, 瞬), 蕩着 liền nhau thành một mark.
	await translateViaApi(page, id, 1);
	const r = await page.request.put(`/api/novels/${id}/chapters/1`, {
		headers: H,
		data: { translated_title: 'Chương 1', translated_text: 'Hoảng đ蕩着 hoàn nhiệt.\nThảm đạm 幽 lục, một 瞬.' }
	});
	expect(r.status()).toBe(200);
	expect((await r.json()).untranslated_han).toBe(4);

	await page.goto(`/novels/${id}`);
	const row = page.locator('ol.rows > li').first();
	await expect(row).toContainText('Còn chữ chưa dịch');

	await page.goto(`/novels/${id}/chapters/1`);
	await expect(page.getByTestId('untranslated-notice')).toContainText('Còn 4 chữ chưa dịch');
	const marks = page.locator('article mark.han-residue');
	await expect(marks).toHaveText(['蕩着', '幽', '瞬']);
	await expect(page.locator('article p.para').first()).toContainText('Hoảng đ蕩着 hoàn nhiệt.');
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, '[data-testid=untranslated-notice] button');
	await shot(page, info, 'untranslated-han');

	// Sửa lại không còn chữ Hán: hết nhãn, hết tô sáng.
	const clean = await page.request.put(`/api/novels/${id}/chapters/1`, {
		headers: H,
		data: { translated_text: 'Rung rinh quanh mình.\nÁnh sáng u lục chợt lóe.' }
	});
	expect((await clean.json()).untranslated_han).toBe(0);
	await page.reload();
	await expect(page.locator('article p.para').first()).toContainText('Rung rinh');
	await expect(page.getByTestId('untranslated-notice')).toHaveCount(0);
	await expect(marks).toHaveCount(0);
	await page.goto(`/novels/${id}`);
	await expect(page.locator('ol.rows > li').first()).not.toContainText('Còn chữ chưa dịch');
});
