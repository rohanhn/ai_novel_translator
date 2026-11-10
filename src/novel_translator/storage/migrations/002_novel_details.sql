-- Thông tin truyện sửa được và ảnh bìa (change edit-novel-details, design D2).
-- Cột mới cho phép NULL: truyện cũ không có tác giả, giới thiệu hay ảnh, không cần backfill.
ALTER TABLE novels
    ADD COLUMN author           TEXT,
    ADD COLUMN description      TEXT,
    ADD COLUMN cover_updated_at TIMESTAMPTZ;

-- Bảng riêng để danh sách thư viện (SELECT n.*) không kéo byte ảnh.
CREATE TABLE novel_covers (
    novel_id BIGINT PRIMARY KEY REFERENCES novels(id) ON DELETE CASCADE,
    mime     TEXT   NOT NULL,
    data     BYTEA  NOT NULL,
    width    INT    NOT NULL,
    height   INT    NOT NULL
);
