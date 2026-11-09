-- 001: schema ban đầu cho PostgreSQL (thay SQLite v0.1, không chuyển dữ liệu cũ).

CREATE TABLE novels (
    id               BIGSERIAL PRIMARY KEY,
    title            TEXT        NOT NULL,
    source_lang      TEXT        NOT NULL DEFAULT 'zh',
    target_lang      TEXT        NOT NULL DEFAULT 'vi',
    glossary_version INT         NOT NULL DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_read_at     TIMESTAMPTZ
);

CREATE TABLE chapters (
    id                BIGSERIAL PRIMARY KEY,
    novel_id          BIGINT      NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    idx               INT         NOT NULL,
    title             TEXT        NOT NULL,
    source_text       TEXT        NOT NULL,
    translated_title  TEXT,
    translated_text   TEXT,
    status            TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'translating', 'translated', 'edited', 'failed')),
    provider          TEXT,
    model             TEXT,
    chain_step        INT,
    glossary_version  INT,
    glossary_outdated BOOLEAN     NOT NULL DEFAULT false,
    possible_omission BOOLEAN     NOT NULL DEFAULT false,
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (novel_id, idx)
);

CREATE TABLE glossary (
    id          BIGSERIAL PRIMARY KEY,
    novel_id    BIGINT NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    source_term TEXT   NOT NULL,
    target_term TEXT   NOT NULL,
    note        TEXT,
    UNIQUE (novel_id, source_term)
);

CREATE TABLE glossary_suggestions (
    novel_id    BIGINT      NOT NULL REFERENCES novels(id) ON DELETE CASCADE,
    source_term TEXT        NOT NULL,
    target_term TEXT        NOT NULL,
    category    TEXT,
    status      TEXT        NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'dismissed')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (novel_id, source_term)
);

CREATE TABLE reading_progress (
    novel_id      BIGINT      PRIMARY KEY REFERENCES novels(id) ON DELETE CASCADE,
    chapter_index INT         NOT NULL,
    position      REAL        NOT NULL DEFAULT 0 CHECK (position >= 0 AND position <= 1),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE preferences (
    key   TEXT  PRIMARY KEY,
    value JSONB NOT NULL
);

CREATE TABLE provider_usage (
    day             DATE NOT NULL,
    step            INT  NOT NULL,
    requests        INT  NOT NULL DEFAULT 0,
    exhausted_until TIMESTAMPTZ,
    PRIMARY KEY (day, step)
);

CREATE TABLE sessions (
    token_hash   TEXT        PRIMARY KEY,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
