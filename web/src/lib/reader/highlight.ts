// Tô sáng chữ Hán còn sót trong bản dịch (spec web-reader "Highlight untranslated characters",
// design D5). Server gửi danh sách chữ được đếm (đã trừ chữ do bộ tên giữ); client chỉ tô
// đúng các chữ đó. Trả về các mảnh text để render bằng {#each}, không dùng {@html}.

export type Piece = { text: string; mark: boolean };

/** Tách `text` thành các mảnh; chữ thuộc `chars` liền nhau gom vào một mảnh `mark`. */
export function splitHan(text: string, chars: ReadonlySet<string>): Piece[] {
	if (chars.size === 0) return [{ text, mark: false }];
	const out: Piece[] = [];
	for (const c of text) {
		const mark = chars.has(c);
		const last = out[out.length - 1];
		if (last && last.mark === mark) last.text += c;
		else out.push({ text: c, mark });
	}
	return out;
}
