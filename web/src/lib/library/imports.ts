// Client cho /api/imports: upload → xem trước → chỉnh ranh giới → xác nhận (design D3).
import { ApiError, api, del, get, post, put } from '../api.js';
import type {
	ImportLang,
	ImportPreview,
	Novel,
	UpdateMode,
	UpdatePreview,
	UpdateResult
} from '../types.js';

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

/** `novelId`: bản xem trước để cập nhật chương của truyện đó (spec chapter-update). */
export function createImport(file: File, novelId?: number): Promise<ImportPreview> {
	const form = new FormData();
	form.append('file', file);
	if (novelId != null) form.append('novel_id', String(novelId));
	return api<ImportPreview>('/api/imports', { method: 'POST', body: form });
}

export function adjustImport(
	id: string,
	boundaries: number[],
	keepFrontMatter: boolean | null
): Promise<ImportPreview> {
	return put<ImportPreview>(`/api/imports/${id}`, {
		boundaries,
		keep_front_matter: keepFrontMatter
	});
}

export function importLines(id: string, start: number, count: number) {
	return get<{ start: number; lines: string[] }>(
		`/api/imports/${id}/lines?start=${start}&count=${Math.min(count, 500)}`
	);
}

export function commitImport(
	id: string,
	body: { title: string; lang: ImportLang; boundaries: number[]; keep_front_matter: boolean | null }
): Promise<Novel> {
	return post<Novel>(`/api/imports/${id}/commit`, body);
}

export type UpdateBody = {
	mode: UpdateMode;
	boundaries: number[];
	keep_front_matter: boolean | null;
	start: number | null;
	delete: number[];
};

export function previewUpdate(id: string, body: UpdateBody): Promise<UpdatePreview> {
	return post<UpdatePreview>(`/api/imports/${id}/update-preview`, body);
}

export function applyUpdate(id: string, body: UpdateBody & { revision: string }) {
	return post<UpdateResult>(`/api/imports/${id}/update`, body);
}

export function discardImport(id: string): Promise<void> {
	return del<void>(`/api/imports/${id}`).catch(() => undefined);
}

/** Bản xem trước hết hạn (410) hoặc không còn: phải upload lại. */
export function isExpired(err: unknown): boolean {
	return err instanceof ApiError && err.status === 410;
}

export function uploadErrorMessage(err: unknown): string {
	if (err instanceof ApiError && err.status === 413)
		return 'File quá lớn. Giới hạn là 50 MB. Chưa có truyện nào được tạo.';
	if (isExpired(err)) return 'Bản xem trước đã hết hạn. Hãy chọn và upload lại file.';
	return err instanceof ApiError ? err.message : 'Không upload được. Thử lại sau.';
}
