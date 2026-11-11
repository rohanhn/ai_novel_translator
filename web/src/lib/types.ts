export type LibraryItem = {
	id: number;
	title: string;
	author: string | null;
	/** Giới thiệu ngắn, giữ xuống dòng. */
	description: string | null;
	/** Ảnh bìa đã upload (URL có phiên bản); null → bìa tự vẽ. */
	cover_url: string | null;
	source_lang: string;
	target_lang: string;
	/** Bản dịch có sẵn (import từ file tiếng Việt): đọc ngay, không dịch bằng model. */
	pretranslated: boolean;
	glossary_version: number;
	created_at: string;
	last_read_at: string | null;
	chapter_count: number;
	translated_count: number;
	last_read_chapter: number | null;
};

export type Novel = Omit<LibraryItem, 'chapter_count' | 'translated_count' | 'last_read_chapter'>;

export type ChapterSummary = {
	index: number;
	title: string;
	translated_title: string | null;
	status: 'pending' | 'translating' | 'translated' | 'edited' | 'failed';
	glossary_outdated: boolean;
	possible_omission: boolean;
	chain_step: number | null;
	job_lane: 'foreground' | 'background' | null;
};

export type Chapter = ChapterSummary & {
	source_text: string;
	translated_text: string | null;
	provider: string | null;
	model: string | null;
	glossary_version: number | null;
};

export type Progress = { chapter_index: number; position: number; updated_at: string };
export type Suggestion = {
	source_term: string;
	target_term: string;
	category: string | null;
	created_at: string;
};
export type Term = { source_term: string; target_term: string; note: string | null };

// --- Import TXT có xem trước (/api/imports) ---
export type SplitWarning = { code: string; message: string; params: Record<string, unknown> };
export type ImportChapter = {
	number: number;
	start_line: number;
	end_line: number;
	title: string;
	chars: number;
	excerpt: string;
	warnings: SplitWarning[];
};
export type ImportPreview = {
	id: string;
	novel_id: number | null;
	filename: string;
	default_title: string;
	detected_lang: 'zh' | 'vi' | 'unknown';
	line_count: number;
	boundaries: number[];
	front_matter: {
		start_line: number;
		end_line: number;
		chars: number;
		excerpt: string;
		keep: boolean;
	} | null;
	chapters: ImportChapter[];
	warnings: SplitWarning[];
};
export type ImportLang = 'zh' | 'vi';

// Cập nhật chương từ TXT (spec chapter-update).
export type UpdateMode = 'append' | 'replace';
export type StoredChapterRef = { index: number; title: string; status: string };
export type FileChapterRef = { position: number; title: string };
export type ProgressMove = {
	from_index: number;
	from_position: number;
	to_index: number;
	to_position: number;
};
export type UpdatePreview = {
	mode: UpdateMode;
	revision: string;
	stored_count: number;
	incoming_count: number;
	warnings: SplitWarning[];
	anchor: { index: number; title: string; position: number; match: 'content' | 'title' } | null;
	needs_start: boolean;
	nothing_new: boolean;
	to_add: FileChapterRef[];
	differing: StoredChapterRef[];
	middle: FileChapterRef[];
	counts: { reuse: number; changed: number; new: number; missing: number } | null;
	changed: StoredChapterRef[];
	missing: StoredChapterRef[];
	new: (FileChapterRef & { index: number })[];
	edited_lost: StoredChapterRef[];
	progress: ProgressMove | null;
};
export type UpdateResult = {
	novel: Novel;
	mode: UpdateMode;
	chapter_count: number;
	added: number;
	reused: number;
	changed: number;
	new: number;
	kept: number;
	deleted: number;
	progress: ProgressMove | null;
};
