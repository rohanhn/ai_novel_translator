import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, shot } from './helpers';

// Import TXT có xem trước (spec web-reader "Import preview screen", "Adjust chapters in the
// preview"; novel-library "Upload novel from the web").
const body = (s: string) => `${s} Trần Bình An ngồi trước cửa ngõ, nhìn mưa xuân rơi trên mái hiên. `.repeat(3);

function vietnameseFile(): string {
	return [
		'Kiếm Lai',
		'Tác giả: Phong Hỏa Hí Chư Hầu',
		'',
		'Chương 1: Kinh trập',
		body('Một.'),
		'Chương 2: Mở cửa',
		body('Hai.'),
		'Đoạn tách thử',
		body('Hai rưỡi.'),
		'Chương 3: Ngõ nhỏ',
		body('Ba.'),
		'Chương 6: Ra trấn',
		body('Sáu.')
	].join('\n');
}

async function openPreview(page: Page, name: string, text = vietnameseFile()) {
	await page.getByRole('button', { name: 'Upload .txt' }).click();
	const dialog = page.getByRole('dialog');
	await dialog.locator('input[type=file]').setInputFiles({
		name: `${name}.txt`,
		mimeType: 'text/plain',
		buffer: Buffer.from(text)
	});
	await dialog.getByRole('button', { name: 'Xem trước' }).click();
	await expect(dialog.getByRole('heading', { name: /Xem trước/ })).toBeVisible();
	return dialog;
}

test('xem trước: cảnh báo đúng chương, gộp, tách, lọc, lưu', async ({ page }, info) => {
	const name = `xemtruoc-${info.project.name}`;
	await login(page);
	const dialog = await openPreview(page, name);

	await expect(dialog.getByText(/4\s+chương/)).toBeVisible();
	await expect(dialog.getByText('tự nhận diện: tiếng Việt')).toBeVisible();
	await expect(dialog.getByLabel('Tiếng Việt · bản dịch có sẵn, đọc ngay')).toBeChecked();
	// Phần đầu file ngắn: mặc định bỏ đi
	await expect(dialog.getByText('Kiếm Lai Tác giả: Phong Hỏa Hí Chư Hầu')).toBeVisible();
	await expect(dialog.getByRole('button', { name: 'Bỏ đi' })).toHaveAttribute('aria-pressed', 'true');
	// Cảnh báo nhảy số nằm ở đúng chương 6, chữ thường
	const ch6 = dialog.locator('ol.chapters > li', { hasText: 'Chương 6: Ra trấn' });
	await expect(ch6).toContainText('Thiếu các chương 4–5');
	await expect(dialog.locator('ol.chapters > li', { hasText: 'Chương 2: Mở cửa' })).not.toContainText(
		'Thiếu'
	);
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'dialog button');
	await shot(page, info, 'import-preview');

	// Lọc chỉ chương có cảnh báo
	await dialog.getByLabel('Chỉ hiện chương có cảnh báo').check();
	await expect(dialog.locator('ol.chapters > li')).toHaveCount(1);
	await dialog.getByLabel('Chỉ hiện chương có cảnh báo').uncheck();

	// Gộp chương 3 vào chương 2
	await dialog.getByRole('button', { name: 'Gộp chương 3 vào chương trước' }).click();
	await expect(dialog.getByText(/3\s+chương/)).toBeVisible();
	await expect(ch6).toContainText('Thiếu các chương 3–5');

	// Tách chương 2 tại một dòng trong thân
	await dialog.getByRole('button', { name: 'Xem các dòng của chương 2' }).click();
	await dialog.getByRole('button', { name: 'Tách chương tại dòng: Đoạn tách thử' }).click();
	await expect(dialog.getByText(/4\s+chương/)).toBeVisible();
	await expect(dialog.locator('ol.chapters > li').nth(2)).toContainText('Đoạn tách thử');

	// Giữ phần đầu file làm "Mở đầu"
	await dialog.getByRole('button', { name: 'Giữ làm chương "Mở đầu"' }).click();
	await expect(dialog.getByText(/5\s+chương/)).toBeVisible();
	await expect(dialog.locator('ol.chapters > li').first()).toContainText('Mở đầu');
	await expectNoHorizontalScroll(page);

	await dialog.getByLabel('Tên truyện').fill(name);
	await dialog.getByRole('button', { name: 'Lưu vào thư viện' }).click();
	await page.waitForURL(/\/novels\/\d+$/);
	const id = Number(page.url().match(/novels\/(\d+)/)![1]);
	const novel = await (await page.request.get(`/api/novels/${id}`)).json();
	expect(novel.pretranslated).toBe(true);
	const chapters = await (await page.request.get(`/api/novels/${id}/chapters`)).json();
	expect(chapters.map((c: { title: string }) => c.title)).toEqual([
		'Mở đầu',
		'Chương 1: Kinh trập',
		'Chương 2: Mở cửa',
		'Đoạn tách thử',
		'Chương 6: Ra trấn'
	]);
	expect(chapters.every((c: { status: string }) => c.status === 'translated')).toBe(true);
	await page.request.delete(`/api/novels/${id}?confirm=true`, { headers: { 'X-Requested-With': 'e2e' } });
});

test('huỷ xem trước thì không tạo truyện', async ({ page }, info) => {
	const name = `huyimport-${info.project.name}`;
	await login(page);
	const dialog = await openPreview(page, name);
	await dialog.getByRole('button', { name: 'Huỷ' }).click();
	await expect(dialog).toBeHidden();
	const lib = await (await page.request.get('/api/novels')).json();
	expect(lib.some((n: { title: string }) => n.title === name)).toBe(false);
});

test('bản xem trước hết hạn: báo và quay về bước chọn file', async ({ page }, info) => {
	await login(page);
	const dialog = await openPreview(page, `hethan-${info.project.name}`);
	await page.route('**/api/imports/*/commit', (r) =>
		r.fulfill({
			status: 410,
			contentType: 'application/json',
			body: JSON.stringify({ detail: 'expired', code: 'draft_expired' })
		})
	);
	await dialog.getByRole('button', { name: 'Lưu vào thư viện' }).click();
	await expect(dialog.getByRole('alert')).toContainText('Bản xem trước đã hết hạn');
	await expect(dialog.getByRole('button', { name: 'Xem trước' })).toBeVisible();
});

test('chọn ngôn ngữ tiếng Trung thì truyện cần dịch', async ({ page }, info) => {
	const name = `doingonngu-${info.project.name}`;
	await login(page);
	const dialog = await openPreview(page, name);
	await dialog.getByLabel('Tiếng Trung · cần dịch').check();
	await dialog.getByLabel('Tên truyện').fill(name);
	await dialog.getByRole('button', { name: 'Lưu vào thư viện' }).click();
	await page.waitForURL(/\/novels\/\d+$/);
	const id = Number(page.url().match(/novels\/(\d+)/)![1]);
	const chapters = await (await page.request.get(`/api/novels/${id}/chapters`)).json();
	expect(chapters.every((c: { status: string }) => c.status === 'pending')).toBe(true);
	await page.request.delete(`/api/novels/${id}?confirm=true`, { headers: { 'X-Requested-With': 'e2e' } });
});
