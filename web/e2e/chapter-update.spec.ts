import { expect, test, type Page } from '@playwright/test';
import {
	expectNoHorizontalScroll,
	expectTouchTargets,
	login,
	novelText,
	setProgress,
	shot,
	translateViaApi,
	uploadNovel
} from './helpers';

// Cập nhật chương từ TXT (spec chapter-update; design D6). Backend chạy provider echo.

async function openChanges(page: Page, novelId: number, text: string) {
	await page.goto(`/novels/${novelId}`);
	await page.getByRole('button', { name: 'Cập nhật từ txt' }).click();
	const dialog = page.getByRole('dialog');
	await dialog.locator('input[type=file]').setInputFiles({
		name: 'moi.txt',
		mimeType: 'text/plain',
		buffer: Buffer.from(text)
	});
	await dialog.getByRole('button', { name: 'Xem cách tách chương' }).click();
	// Bước tách chương: không có ô tên truyện / ngôn ngữ
	await expect(dialog.getByRole('button', { name: 'Tiếp tục · xem thay đổi' })).toBeVisible();
	await expect(dialog.getByLabel('Tên truyện')).toHaveCount(0);
	await dialog.getByRole('button', { name: 'Tiếp tục · xem thay đổi' }).click();
	await expect(dialog.getByRole('group', { name: /Cách cập nhật/ })).toBeVisible();
	return dialog;
}

async function chapters(page: Page, novelId: number) {
	return (await (await page.request.get(`/api/novels/${novelId}/chapters`)).json()) as {
		index: number;
		title: string;
		status: string;
	}[];
}

test('thêm chương mới: mục lục tăng, chương cũ giữ bản dịch', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `them-${info.project.name}`, 3, 8, true);
	await translateViaApi(page, id, 2);

	const dialog = await openChanges(page, id, novelText([1, 2, 3, 4, 5], 8, [], true));
	const confirm = dialog.getByRole('button', { name: /Xác nhận/ });
	await expect(confirm).toBeDisabled(); // chưa chọn chế độ
	await dialog.getByText('Thêm chương mới', { exact: true }).click();
	await expect(dialog.getByText(/Điểm nối: sau chương\s+3/)).toBeVisible();
	await expect(dialog.getByText(/\+2\s+chương mới/)).toBeVisible();
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'dialog button, dialog label.mode');
	await shot(page, info, 'update-append');

	await dialog.getByRole('button', { name: 'Xác nhận thêm chương' }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(page.getByText('Đã thêm 2 chương mới. Truyện có 5 chương.')).toBeVisible();
	await expect(page.locator('ol.rows > li')).toHaveCount(5);
	const chs = await chapters(page, id);
	expect(chs.map((c) => c.status)).toEqual(['pending', 'translated', 'pending', 'pending', 'pending']);
});

test('tải lại cả bộ: chương sửa thành chưa dịch, chương thiếu bị xoá, tiến độ đúng chương', async ({
	page
}, info) => {
	await login(page);
	const id = await uploadNovel(page, `tailai-${info.project.name}`, 4, 8, true);
	await translateViaApi(page, id, 2);
	await translateViaApi(page, id, 3);
	await setProgress(page, id, 4, 0.5);

	// File mới: chương 2 bị sửa, chương 3 không còn, thêm chương 5.
	const dialog = await openChanges(page, id, novelText([1, 2, 4, 5], 8, [2], true));
	await dialog.getByText('Tải lại cả bộ', { exact: true }).click();
	const counts = dialog.locator('dl.counts');
	await expect(counts).toContainText('Giữ bản dịch2');
	await expect(counts).toContainText('Nội dung đổi · dịch lại1');
	await expect(counts).toContainText('Chương mới1');
	await expect(counts).toContainText('Không còn trong file1');
	await dialog.getByLabel(/Xoá chương 3 · 第3章 标题3/).check();
	await expect(dialog.getByText('Tiến độ đọc: chương 4 (50%) → chương 3 (50%)')).toBeVisible();
	await expectNoHorizontalScroll(page);
	await expectTouchTargets(page, 'dialog button, dialog label.check, dialog label.mode');
	await shot(page, info, 'update-replace');

	await dialog.getByRole('button', { name: 'Xác nhận tải lại' }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	await expect(page.getByText(/Đã tải lại cả bộ/)).toBeVisible();
	const chs = await chapters(page, id);
	expect(chs.map((c) => [c.title, c.status])).toEqual([
		['第1章 标题1', 'pending'],
		['第2章 标题2', 'pending'],
		['第4章 标题4', 'pending'],
		['第5章 标题5', 'pending']
	]);
	const progress = await (await page.request.get(`/api/novels/${id}/progress`)).json();
	expect([progress.chapter_index, progress.position]).toEqual([3, 0.5]);
});

test('huỷ cập nhật: không đổi gì', async ({ page }, info) => {
	await login(page);
	const id = await uploadNovel(page, `huy-${info.project.name}`, 2, 8, true);
	const dialog = await openChanges(page, id, novelText([1, 2, 3], 8, [], true));
	await dialog.getByText('Tải lại cả bộ', { exact: true }).click();
	await expect(dialog.locator('dl.counts')).toBeVisible();
	await dialog.getByRole('button', { name: 'Huỷ' }).click();
	await expect(page.getByRole('dialog')).toHaveCount(0);
	expect((await chapters(page, id)).length).toBe(2);
});
