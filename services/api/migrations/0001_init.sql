-- Схема VoiceTranscribator, версия 1.
-- Правила: только добавляющие изменения в дальнейшем; аудио и тексты хранятся раздельно;
-- отпечатки голосов (биометрия) — в отдельной схеме biometry, чтобы их можно было
-- удалить одним контролируемым действием и чтобы право доступа на них выдавалось отдельно.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE users (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email           text NOT NULL UNIQUE,
    display_name    text NOT NULL,
    password_hash   text NOT NULL,
    role            text NOT NULL DEFAULT 'member' CHECK (role IN ('owner', 'member', 'viewer')),
    preset          text NOT NULL DEFAULT 'balanced',
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE sessions (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title           text NOT NULL DEFAULT 'Разговор',
    started_at      timestamptz NOT NULL DEFAULT now(),
    ended_at        timestamptz,
    status          text NOT NULL DEFAULT 'recording'
                    CHECK (status IN ('recording', 'paused', 'processing', 'ready', 'failed')),
    language        text NOT NULL DEFAULT 'ru',
    asr_provider    text NOT NULL DEFAULT 'fake',
    audio_path      text,
    duration_s      numeric(12, 2) NOT NULL DEFAULT 0
);
CREATE INDEX sessions_by_user_started ON sessions (user_id, started_at DESC);

CREATE TABLE speakers (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    label           text NOT NULL,
    display_name    text,
    verdict         text NOT NULL DEFAULT 'unknown'
                    CHECK (verdict IN ('owner', 'member', 'foreign', 'noise', 'unknown')),
    UNIQUE (session_id, label)
);

CREATE TABLE segments (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    speaker_id      uuid REFERENCES speakers(id) ON DELETE SET NULL,
    start_s         numeric(10, 2) NOT NULL,
    end_s           numeric(10, 2) NOT NULL,
    text            text NOT NULL,
    confidence      real NOT NULL DEFAULT 1.0,
    is_volatile     boolean NOT NULL DEFAULT false,
    CHECK (end_s >= start_s)
);
CREATE INDEX segments_by_session_time ON segments (session_id, start_s) WHERE NOT is_volatile;

CREATE TABLE digests (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    version         int NOT NULL DEFAULT 1,
    summary         text[] NOT NULL DEFAULT '{}',
    decisions       text[] NOT NULL DEFAULT '{}',
    open_questions  text[] NOT NULL DEFAULT '{}',
    model           text NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_id, version)
);

CREATE TABLE items (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id      uuid NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    digest_id       uuid REFERENCES digests(id) ON DELETE SET NULL,
    kind            text NOT NULL CHECK (kind IN ('task', 'meeting', 'reminder', 'decision', 'question')),
    title           text NOT NULL,
    owner           text,
    due_at          timestamptz,
    priority        text NOT NULL DEFAULT 'medium' CHECK (priority IN ('low', 'medium', 'high')),
    evidence        jsonb NOT NULL,
    status          text NOT NULL DEFAULT 'draft'
                    CHECK (status IN ('draft', 'approved', 'sent', 'declined')),
    approved_by     uuid REFERENCES users(id),
    approved_at     timestamptz
);
CREATE INDEX items_by_session_status ON items (session_id, status);

CREATE TABLE integrations (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target          text NOT NULL CHECK (target IN ('helper', 'jira', 'bitrix24', 'webhook')),
    base_url        text NOT NULL,
    credentials_enc bytea,
    created_at      timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, target)
);

CREATE TABLE usage (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id      uuid REFERENCES sessions(id) ON DELETE SET NULL,
    asr_seconds     numeric(12, 2) NOT NULL DEFAULT 0,
    llm_tokens      int NOT NULL DEFAULT 0,
    money_rub       numeric(12, 2) NOT NULL DEFAULT 0,
    day             date NOT NULL DEFAULT current_date
);
CREATE INDEX usage_by_user_day ON usage (user_id, day);

CREATE SCHEMA IF NOT EXISTS biometry;
CREATE TABLE biometry.voiceprints (
    id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id         uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    label           text NOT NULL,
    embedding       bytea NOT NULL,
    model           text NOT NULL DEFAULT 'ecapa',
    consent_at      timestamptz NOT NULL,
    created_at      timestamptz NOT NULL DEFAULT now()
);
