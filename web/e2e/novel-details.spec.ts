import { expect, test, type Page } from '@playwright/test';
import { expectNoHorizontalScroll, expectTouchTargets, login, shot, uploadNovel } from './helpers';

// Sửa thông tin truyện (spec web-reader "Edit novel details screen", "Cover selection in the edit
// form", "Edit form layout", "Novel details display", "Cover display with fallback").
// Ảnh từ link: /api/covers/fetch được giả bằng page.route, không có request nào ra internet.

const H = { 'X-Requested-With': 'e2e' };
const PNG = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAADwAAABaCAIAAABrM6JiAAAAeElEQVR4nO3OQQ3AIAAAMUDDdPJG/jzscWRJq6DzOXv8zbod+EK6Il2RrkhXpCvSFemKdEW6Il2RrkhXpCvSFemKdEW6Il2RrkhXpCvSFemKdEW6Il2RrkhXpCvSFemKdEW6Il2RrkhXpCvSFemKdEW6Il2RrkhXXsVoAa716YemAAAAAElFTkSuQmCC',
	'base64'
); // 60×90
const PNG_WIDE = Buffer.from(
	'iVBORw0KGgoAAAANSUhEUgAAAFoAAAA8CAIAAABpZzoSAAAAjElEQVR4nO3QMRHAIADAQEBIZ2QjtVOHKKDDv4Jc5tnP4LNuB/yLHWFH2BF2hB1hR9gRdoQdYUfYEXaEHWFH2BF2hB1hR9gRdoQdYUfYEXaEHWFH2BF2hB1hR9gRdoQdYUfYEXaEHWFH2BF2hB1hR9gRdoQdYUfYEXaEHWFH2BF2hB1hR9gRdoQdYUe8NfoBXsjiAZ0AAAAASUVORK5CYII=',
	'base64'
); // 90×60
const GIF = Buffer.from('R0lGODdhCAAIAIEAAAAAAAAAAAAAAAAAACwAAAAACAAIAAAIDwABCBxIsKDBgwgTKkwYEAA7', 'base64');

async function openEdit(page: Page, id: number) {
	await page.goto(`/novels/${id}`);
	await page.getByRole('button', { name: 'Sửa thông tin' }).click();
	const dialog = page.getByRole('dialog', { name: /Sửa thông tin/ });
	await expect(dialog).toBeVisible();
	return dialog;
}

async function novel(page: Page, id: number) {
	return (await page.request.get(`/api/novels/${id}`)).json();
}

async function cleanup(page: Page, id: number) {
	await page.request.delete(`/api/novels/${id}?confirm=true`, { headers: H });
}

test('sửa tên, tác giả, giới thiệu: hiện ở trang truyện và thư viện, tìm theo tác giả', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `suathongtin-${info.project.name}`, 2);
	const dialog = await openEdit(page, id);

	// bố cục: nút Lưu trong khung nhìn, không cuộn ngang, vùng chạm đủ lớn
	const save = await dialog.getByRole('button', { name: 'Lưu' }).boundingBox();
	expect(save!.y + save!.height).toBeLessThanOrEqual(page.viewportSize()!.height);
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'dialog[open] button');
	await shot(page, info, 'edit-novel');

	const title = `Kiếm Lai ${info.project.name}`;
	const author = `Phong Hỏa ${info.project.name}`;
	await dialog.getByLabel('Tên truyện').fill(title);
	await dialog.getByLabel('Tác giả').fill(author);
	await dialog.getByLabel('Giới thiệu ngắn').fill('Dòng giới thiệu một.\nDòng giới thiệu hai.');
	await expect(dialog.getByText('41/2000')).toBeVisible();
	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog).toBeHidden();

	await expect(page.getByRole('heading', { level: 1 })).toHaveText(title);
	await expect(page.getByText(`Tác giả: ${author}`)).toBeVisible();
	const intro = page.locator('.intro-text');
	await expect(intro).toHaveText('Dòng giới thiệu một.\nDòng giới thiệu hai.');
	expect((await intro.innerText()).split('\n')).toHaveLength(2);
	await expect(page).toHaveTitle(new RegExp(title));

	await page.goto('/');
	const card = page.locator('li.card', { hasText: title });
	await expect(card).toContainText(author);
	await page.getByRole('searchbox').fill(`hỏa ${info.project.name}`.toUpperCase());
	await expect(page.locator('li.card')).toHaveCount(1);
	await expect(page.locator('li.card')).toContainText(title);
	await page.getByRole('searchbox').fill('khong-co-tac-gia-nay');
	await expect(page.locator('li.card')).toHaveCount(0);
	await cleanup(page, id);
});

test('lỗi từ server hiện cạnh ô và giữ dữ liệu đã nhập', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `loitruong-${info.project.name}`, 1);
	const dialog = await openEdit(page, id);
	await dialog.getByLabel('Tác giả').fill('Tác giả giữ lại');
	await dialog.getByLabel('Tên truyện').fill('   ');
	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog.getByRole('alert')).toHaveText('Tên truyện không được để trống.');
	await expect(dialog.getByLabel('Tên truyện')).toHaveAttribute('aria-invalid', 'true');
	await expect(dialog.getByLabel('Tác giả')).toHaveValue('Tác giả giữ lại');
	expect((await novel(page, id)).author).toBeNull();
	await cleanup(page, id);
});

test('chọn ảnh từ máy, xem trước, lưu; gỡ ảnh thì về bìa tự vẽ', async ({ page }, info) => {
	await login(page);
	const name = `biaanh-${info.project.name}`;
	const id = await uploadNovel(page, name, 1);
	let dialog = await openEdit(page, id);
	await dialog.getByLabel('Chọn ảnh bìa từ máy').setInputFiles({ name: 'bia.png', mimeType: 'image/png', buffer: PNG });
	await expect(dialog.locator('.cover img')).toHaveAttribute('src', /^blob:/);
	await expect(dialog.getByText('Ảnh mới, sẽ lưu khi bấm Lưu.')).toBeVisible();
	expect((await novel(page, id)).cover_url).toBeNull(); // chưa lưu
	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog).toBeHidden();

	const coverUrl = (await novel(page, id)).cover_url as string;
	expect(coverUrl).toMatch(new RegExp(`^/api/novels/${id}/cover\\?v=\\d+$`));
	await expect(page.locator('.hero .cover img')).toHaveAttribute('src', coverUrl);
	await page.goto('/');
	const card = page.locator('li.card', { hasText: name });
	await expect(card.locator('.cover img')).toHaveAttribute('src', coverUrl);
	await expect(card.locator('.cover img')).toHaveAttribute('alt', '');
	expect(await card.locator('.cover img').evaluate((i: HTMLImageElement) => i.naturalWidth)).toBe(60);

	dialog = await openEdit(page, id);
	await dialog.getByRole('button', { name: 'Gỡ ảnh' }).click();
	await expect(dialog.locator('.cover img')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog).toBeHidden();
	await expect(page.locator('.hero .cover img')).toHaveCount(0);
	await expect(page.locator('.hero .cover .seal')).toBeVisible();
	expect((await novel(page, id)).cover_url).toBeNull();
	await cleanup(page, id);
});

test('dán link: server tải ảnh, trình duyệt không gọi tới host của link', async ({ page }, info) => {
	await login(page);
	const name = `bialink-${info.project.name}`;
	const id = await uploadNovel(page, name, 1);
	const toLinkHost: string[] = [];
	page.on('request', (r) => {
		if (r.url().includes('anh.example')) toLinkHost.push(r.url());
	});
	const fetchBodies: string[] = [];
	await page.route('**/api/covers/fetch', async (route) => {
		const body = route.request().postDataJSON() as { url: string };
		fetchBodies.push(body.url);
		await new Promise((r) => setTimeout(r, 400));
		if (body.url.endsWith('/hong.png'))
			return route.fulfill({
				status: 400,
				contentType: 'application/json',
				body: JSON.stringify({
					detail: 'Không tải được ảnh từ link này (máy chủ trả lỗi 404).',
					field: 'cover_url',
					reason: 'download_failed'
				})
			});
		return route.fulfill({ status: 200, contentType: 'image/png', body: PNG_WIDE });
	});

	const dialog = await openEdit(page, id);
	const linkField = dialog.getByLabel('Hoặc dán link ảnh');
	await linkField.fill('https://anh.example/bia.png');
	await dialog.getByRole('button', { name: 'Lấy ảnh' }).click();
	await expect(dialog.getByRole('button', { name: 'Đang tải ảnh…' })).toBeDisabled();
	await expect(dialog.locator('.cover img')).toHaveAttribute('src', /^blob:/);
	const preview = await dialog.locator('.cover img').getAttribute('src');

	// link hỏng: báo cạnh ô link, ảnh xem trước giữ nguyên
	await linkField.fill('https://anh.example/hong.png');
	await linkField.press('Enter');
	await expect(dialog.getByText('Không tải được ảnh từ link này (máy chủ trả lỗi 404).')).toBeVisible();
	await expect(linkField).toHaveAttribute('aria-invalid', 'true');
	await expect(dialog.locator('.cover img')).toHaveAttribute('src', preview!);
	expect(await dialog.isVisible()).toBe(true); // Enter trong ô link không gửi form

	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog).toBeHidden();
	const saved = await novel(page, id);
	expect(saved.cover_url).not.toBeNull();
	const img = await page.request.get(saved.cover_url);
	expect(img.headers()['content-type']).toBe('image/webp');
	await page.goto('/');
	await expect(page.locator('li.card', { hasText: name }).locator('.cover img')).toHaveAttribute('src', saved.cover_url);

	expect(fetchBodies).toEqual(['https://anh.example/bia.png', 'https://anh.example/hong.png']);
	expect(toLinkHost).toEqual([]);
	await cleanup(page, id);
});

test('file không hỗ trợ hoặc quá 10 MB: báo lỗi, không upload', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `filesai-${info.project.name}`, 1);
	const puts: string[] = [];
	page.on('request', (r) => {
		if (r.method() === 'PUT' && r.url().includes('/cover')) puts.push(r.url());
	});
	const dialog = await openEdit(page, id);
	const input = dialog.getByLabel('Chọn ảnh bìa từ máy');
	await input.setInputFiles({ name: 'dong.gif', mimeType: 'image/gif', buffer: GIF });
	await expect(dialog.getByRole('alert')).toHaveText('Chỉ nhận ảnh JPG, PNG hoặc WebP.');
	await input.setInputFiles({
		name: 'to.jpg',
		mimeType: 'image/jpeg',
		buffer: Buffer.alloc(10 * 1024 * 1024 + 1, 1)
	});
	await expect(dialog.getByRole('alert')).toContainText('lớn hơn 10 MB');
	await expect(dialog.locator('.cover img')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Lưu' }).click();
	await expect(dialog).toBeHidden();
	expect(puts).toEqual([]);
	expect((await novel(page, id)).cover_url).toBeNull();
	await cleanup(page, id);
});

test('huỷ thì không lưu gì', async ({ page }, info) => {
	await login(page);
	const name = `huysua-${info.project.name}`;
	const id = await uploadNovel(page, name, 1);
	const dialog = await openEdit(page, id);
	await dialog.getByLabel('Tên truyện').fill('Tên bị huỷ');
	await dialog.getByLabel('Tác giả').fill('Tác giả bị huỷ');
	await dialog.getByLabel('Chọn ảnh bìa từ máy').setInputFiles({ name: 'bia.png', mimeType: 'image/png', buffer: PNG });
	await dialog.getByRole('button', { name: 'Huỷ' }).click();
	await expect(dialog).toBeHidden();
	await expect(page.getByRole('heading', { level: 1 })).toHaveText(name);
	const n = await novel(page, id);
	expect([n.title, n.author, n.cover_url]).toEqual([name, null, null]);
	// mở lại: form lấy lại giá trị hiện tại, không còn dữ liệu đã huỷ
	const again = await openEdit(page, id);
	await expect(again.getByLabel('Tên truyện')).toHaveValue(name);
	await expect(again.getByLabel('Tác giả')).toHaveValue('');
	await cleanup(page, id);
});

test('ảnh bìa không tải được thì hiện bìa tự vẽ', async ({ page }, info) => {
	await login(page);
	const name = `bialoi-${info.project.name}`;
	const id = await uploadNovel(page, name, 1);
	await page.request.put(`/api/novels/${id}/cover`, {
		headers: H,
		multipart: { file: { name: 'bia.png', mimeType: 'image/png', buffer: PNG } }
	});
	await page.route(`**/api/novels/${id}/cover*`, (r) => r.fulfill({ status: 404, body: '' }));
	await page.goto('/');
	const card = page.locator('li.card', { hasText: name });
	await expect(card.locator('.cover .seal')).toBeVisible();
	await expect(card.locator('.cover img')).toHaveCount(0);
	await cleanup(page, id);
});
