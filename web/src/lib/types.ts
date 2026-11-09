export type LibraryItem = {
	id: number;
	title: string;
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
};

export type Chapter = ChapterSummary & {
	source_text: string;
	translated_text: string | null;
	provider: string | null;
	model: string | null;
	chain_step: number | null;
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
