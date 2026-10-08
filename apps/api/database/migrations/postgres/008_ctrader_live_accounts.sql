-- Allow discovered live accounts. Trading execution remains disabled.
DO $$
DECLARE r record;
BEGIN
  FOR r IN
    SELECT con.conname
    FROM pg_constraint con
    JOIN pg_class rel ON rel.oid = con.conrelid
    WHERE rel.relname = 'ctrader_accounts' AND con.contype = 'c'
  LOOP
    EXECUTE 'ALTER TABLE ctrader_accounts DROP CONSTRAINT ' || quote_ident(r.conname);
  END LOOP;
END $$;
ALTER TABLE ctrader_accounts ADD CONSTRAINT ctrader_accounts_environment_check CHECK (environment IN ('demo', 'live'));
