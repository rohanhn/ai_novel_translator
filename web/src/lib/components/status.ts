// Nhãn trạng thái chương: luôn bằng chữ thường, rõ nghĩa (spec web-reader "Plain-language labels").
export type ChipKind =
	| 'pending'
	| 'translating'
	| 'prefetching'
	| 'translated'
	| 'edited'
	| 'failed'
	| 'glossary_outdated'
	| 'fallback'
	| 'possible_omission';

export const CHIP_LABELS: Record<ChipKind, string> = {
	pending: 'Chưa dịch',
	translating: 'Đang dịch',
	prefetching: 'Đang dịch · chuẩn bị trước',
	translated: 'Đã dịch',
	edited: 'Đã biên tập',
	failed: 'Lỗi',
	glossary_outdated: 'Bộ tên đã đổi',
	fallback: 'Model dự phòng',
	possible_omission: 'Có thể thiếu đoạn'
};

export type ChapterFlags = {
	status: string;
	glossary_outdated?: boolean;
	possible_omission?: boolean;
	chain_step?: number | null;
};

/** Các nhãn cần hiện cho một chương (trạng thái chính + cờ phụ). */
export function chipsFor(ch: ChapterFlags): ChipKind[] {
	const kinds: ChipKind[] = [(ch.status in CHIP_LABELS ? ch.status : 'pending') as ChipKind];
	if (ch.chain_step != null && ch.chain_step > 1) kinds.push('fallback');
	if (ch.glossary_outdated) kinds.push('glossary_outdated');
	if (ch.possible_omission) kinds.push('possible_omission');
	return kinds;
}
