-- HackRadar rev 3.1 rubric rebuild.
--
-- The old 4-criterion rubric (open/novelty/wow/build) is reframed as
-- tech-discovery (usability/innovation/underexploited/wow). Old columns
-- are left in place for back-compat with existing scan rows; new columns
-- store the rev 3.1 scores plus prompt_version for score cache keying.
--
-- SQLite doesn't support ADD COLUMN IF NOT EXISTS, so each ALTER is
-- wrapped in a trigger-less "ignore duplicate column" pattern at the
-- Python layer (db.init catches the OperationalError per-statement).

ALTER TABLE scores ADD COLUMN usability_score REAL;
ALTER TABLE scores ADD COLUMN innovation_score REAL;
ALTER TABLE scores ADD COLUMN underexploited_score REAL;
ALTER TABLE scores ADD COLUMN what_the_tech_does TEXT;
ALTER TABLE scores ADD COLUMN key_capabilities TEXT;
ALTER TABLE scores ADD COLUMN idea_sparks TEXT;
ALTER TABLE scores ADD COLUMN prompt_version TEXT;

CREATE INDEX IF NOT EXISTS idx_scores_prompt_version ON scores(prompt_version);
