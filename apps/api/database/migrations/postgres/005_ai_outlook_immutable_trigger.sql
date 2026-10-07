-- Published outlooks are immutable. A rule blocks INSERT ... ON CONFLICT on PostgreSQL, so enforce it with a trigger instead.
DROP RULE IF EXISTS ai_outlook_symbol_no_update ON ai_outlook_symbol;
CREATE OR REPLACE FUNCTION ai_outlook_symbol_immutable() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'published outlooks are immutable';
END
$$;
DROP TRIGGER IF EXISTS ai_outlook_symbol_immutable ON ai_outlook_symbol;
CREATE TRIGGER ai_outlook_symbol_immutable BEFORE UPDATE ON ai_outlook_symbol FOR EACH ROW EXECUTE FUNCTION ai_outlook_symbol_immutable();
