export type LibraryItem = {
	id: number;
	title: string;
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
