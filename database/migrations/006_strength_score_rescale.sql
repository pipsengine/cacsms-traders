-- Scores are now anchored at raw 0 (EarnForex sign); clear old-scale scores so the engine backfills them.
UPDATE mi_strength_snapshot SET score = NULL;
