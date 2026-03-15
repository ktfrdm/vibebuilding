-- Vibe bot: initial schema for Supabase
-- Run in Supabase SQL Editor after creating the project

-- Meetings (organizer-created events)
CREATE TABLE IF NOT EXISTS meetings (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    slots JSONB NOT NULL DEFAULT '[]',
    status TEXT NOT NULL DEFAULT 'created',
    creator_user_id BIGINT NOT NULL,
    chat_id BIGINT NOT NULL,
    chosen_slot_id INTEGER,
    place TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Participants (replies per meeting)
CREATE TABLE IF NOT EXISTS participants (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    chosen_slot_ids JSONB NOT NULL DEFAULT '[]',
    pending_confirm BOOLEAN NOT NULL DEFAULT FALSE,
    first_name TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (meeting_id, user_id)
);

-- Draft slot selection (before participant clicks "Готово")
CREATE TABLE IF NOT EXISTS participant_selection (
    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
    user_id BIGINT NOT NULL,
    slot_indices JSONB NOT NULL DEFAULT '[]',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (meeting_id, user_id)
);

-- Organizer flow state (title / slots / place step)
CREATE TABLE IF NOT EXISTS user_states (
    user_id BIGINT PRIMARY KEY,
    step TEXT NOT NULL DEFAULT 'idle',
    data JSONB NOT NULL DEFAULT '{}',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for common lookups
CREATE INDEX IF NOT EXISTS idx_meetings_creator ON meetings(creator_user_id);
CREATE INDEX IF NOT EXISTS idx_participants_meeting ON participants(meeting_id);
CREATE INDEX IF NOT EXISTS idx_participant_selection_meeting ON participant_selection(meeting_id);
