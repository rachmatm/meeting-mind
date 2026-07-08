-- 0003_pics_projects_meetings.sql
-- Phase 1+2 schema: PICs, Projects, Meetings per blueprint section 5.
-- Idempotent: safe to re-run.

-- =========================================================================
-- PICs (Person-In-Charge) - can be individual or group/team
-- =========================================================================

CREATE TABLE IF NOT EXISTS pics (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL UNIQUE,  -- unique identifier (e.g., email, slack ID, team name)
    name TEXT NOT NULL,
    type TEXT DEFAULT 'person' CHECK (type IN ('person', 'group')),
    email TEXT,
    slack_id TEXT,
    divisions TEXT[],  -- e.g., ['engineering', 'design', 'marketing']
    responsibilities TEXT[],  -- e.g., ['frontend', 'backend', 'devops']
    skills TEXT[],  -- e.g., ['react', 'python', 'figma']
    max_concurrent_tasks INT DEFAULT 5,
    manager_id UUID REFERENCES pics(id),
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- PIC contact methods (multiple per PIC - for groups, multiple people)
CREATE TABLE IF NOT EXISTS pic_contacts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pic_id UUID REFERENCES pics(id) ON DELETE CASCADE,
    contact_type TEXT NOT NULL CHECK (contact_type IN ('whatsapp', 'email', 'slack')),
    contact_value TEXT NOT NULL,
    person_name TEXT NOT NULL,    -- person's name for polite greeting
    is_primary BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Projects table
CREATE TABLE IF NOT EXISTS projects (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    description TEXT,
    notion_page_id TEXT,  -- Notion integration
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Project-PIC junction (many-to-many)
CREATE TABLE IF NOT EXISTS project_pics (
    project_id UUID REFERENCES projects(id) ON DELETE CASCADE,
    pic_id UUID REFERENCES pics(id) ON DELETE CASCADE,
    role TEXT DEFAULT 'member',  -- lead, member, reviewer
    joined_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (project_id, pic_id)
);

-- Meetings table (transcripts and summaries)
CREATE TABLE IF NOT EXISTS meetings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID REFERENCES projects(id) ON DELETE SET NULL,
    title TEXT,
    transcript TEXT NOT NULL,
    summary JSONB,  -- {summary, key_points[], action_items[]}
    audio_url TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Tasks table (extended from 0001)
ALTER TABLE tasks DROP COLUMN IF EXISTS title;
ALTER TABLE tasks DROP COLUMN IF EXISTS status;
ALTER TABLE tasks DROP COLUMN IF EXISTS deadline;
ALTER TABLE tasks DROP COLUMN IF EXISTS user_id;

ALTER TABLE tasks ADD COLUMN IF NOT EXISTS project_id UUID REFERENCES projects(id) ON DELETE CASCADE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS division TEXT NOT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS description TEXT NOT NULL;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS pic_id UUID REFERENCES pics(id);
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS deadline DATE;
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'todo' CHECK (status IN ('todo', 'in_progress', 'done'));
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS meeting_id UUID REFERENCES meetings(id);