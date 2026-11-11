-- Số chữ Hán còn sót trong bản dịch (change flag-untranslated-han, design D2, D7).
ALTER TABLE chapters ADD COLUMN untranslated_han INT NOT NULL DEFAULT 0;

-- Tính sẵn cho bản dịch đã có, cùng quy tắc với domain/han_residue.py: đếm chữ Hán trong
-- tiêu đề + nội dung dịch, bỏ các chữ Hán có trong bản dịch bộ tên của cùng truyện.
WITH kept AS (
    SELECT g.novel_id, string_agg(DISTINCT c, '') AS chars
    FROM glossary g, regexp_split_to_table(g.target_term, '') AS c
    WHERE c ~ '[一-鿿㐀-䶿豈-﫿\U00020000-\U0002a6df]'
    GROUP BY g.novel_id
), counted AS (
    SELECT ch.id,
           regexp_count(
               CASE WHEN k.chars IS NULL THEN x.t
                    ELSE regexp_replace(x.t, '[' || k.chars || ']', '', 'g') END,
               '[一-鿿㐀-䶿豈-﫿\U00020000-\U0002a6df]') AS n
    FROM chapters ch
    CROSS JOIN LATERAL (
        SELECT coalesce(ch.translated_title, '') || E'\n' || coalesce(ch.translated_text, '') AS t
    ) x
    LEFT JOIN kept k ON k.novel_id = ch.novel_id
    WHERE ch.translated_text IS NOT NULL
)
UPDATE chapters c SET untranslated_han = counted.n
FROM counted
WHERE c.id = counted.id AND counted.n > 0;
