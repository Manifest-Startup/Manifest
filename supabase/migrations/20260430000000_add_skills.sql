-- Add skills to users and required_skills to ideas

ALTER TABLE users
  ADD COLUMN IF NOT EXISTS skills TEXT[] NOT NULL DEFAULT '{}';

ALTER TABLE ideas
  ADD COLUMN IF NOT EXISTS required_skills TEXT[] NOT NULL DEFAULT '{}';
