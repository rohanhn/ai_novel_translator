// Client sửa thông tin truyện + ảnh bìa (design D4, D6). Ảnh từ link do SERVER tải về:
// trình duyệt không bao giờ tự mở link người dùng dán.
import { goto } from '$app/navigation';
import { ApiError, CSRF_HEADER, api, del, loginUrl, patch } from '../api.js';
import type { Novel } from '../types.js';

export const MAX_COVER_BYTES = 10 * 1024 * 1024;
export const TITLE_MAX = 200;
export const AUTHOR_MAX = 100;
export const DESCRIPTION_MAX = 2000;

const COVER_TYPES = ['image/jpeg', 'image/png', 'image/webp'];
const COVER_EXT = /\.(jpe?g|png|webp)$/i;

export type DetailsPatch = { title?: string; author?: string | null; description?: string | null };
export type DetailsField = 'title' | 'author' | 'description' | 'cover' | 'cover_url';

export function updateDetails(id: number, body: DetailsPatch): Promise<Novel> {
	return patch<Novel>(`/api/novels/${id}`, body);
}

export function uploadCover(id: number, image: Blob, name = 'bia.webp'): Promise<Novel> {
	const form = new FormData();
	form.append('file', image, name);
	return api<Novel>(`/api/novels/${id}/cover`, { method: 'PUT', body: form });
}

export function removeCover(id: number): Promise<null> {
	return del<null>(`/api/novels/${id}/cover`);
}

/** Lỗi khi chọn file ảnh từ máy (kiểm trước khi gửi), hoặc null nếu dùng được. */
export function coverFileProblem(file: File): string | null {
	const typeOk = file.type ? COVER_TYPES.includes(file.type) : COVER_EXT.test(file.name);
	if (!typeOk) return 'Chỉ nhận ảnh JPG, PNG hoặc WebP.';
	if (file.size > MAX_COVER_BYTES) return 'Ảnh lớn hơn 10 MB. Hãy chọn ảnh nhỏ hơn.';
	if (file.size === 0) return 'File rỗng.';
	return null;
}

/** Server tải ảnh từ link và trả ảnh đã xử lý (WebP) để xem trước; chưa lưu gì. */
export async function fetchCoverFromUrl(url: string): Promise<Blob> {
	const res = await fetch('/api/covers/fetch', {
		method: 'POST',
		credentials: 'same-origin',
		headers: { 'Content-Type': 'application/json', [CSRF_HEADER]: 'fetch' },
		body: JSON.stringify({ url })
	});
	if (res.status === 401) {
		await goto(loginUrl(), { replaceState: true });
		throw new ApiError(401, { detail: 'Chưa đăng nhập.' });
	}
	if (!res.ok) {
		let body: Record<string, unknown>;
		try {
			body = await res.json();
		} catch {
			body = { detail: 'Không tải được ảnh từ link này.' };
		}
		throw new ApiError(res.status, body);
	}
	return res.blob();
}

/** Trường bị lỗi theo phản hồi 400 của API (`field`), nếu có. */
export function errorField(err: unknown): DetailsField | null {
	if (!(err instanceof ApiError)) return null;
	const f = err.body.field;
	if (f === 'title' || f === 'author' || f === 'description' || f === 'cover' || f === 'cover_url')
		return f;
	return err.status === 413 ? 'cover' : null;
}

export function errorMessage(err: unknown): string {
	if (err instanceof ApiError && err.status === 413) return 'Ảnh lớn hơn 10 MB.';
	return err instanceof ApiError ? err.message : 'Không lưu được. Thử lại sau.';
}
