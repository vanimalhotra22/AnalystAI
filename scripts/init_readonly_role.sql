-- Least-privilege role for the agent's SQL tool.
-- Runs automatically on first container start (see docker-compose.yml).
--
-- The validator in app/agents/sql_tool.py is the first gate; this role is the
-- second. A SELECT-only role means a bug in the validator still cannot mutate
-- or delete business data.

CREATE ROLE insight_ro WITH LOGIN PASSWORD 'insight_ro';

GRANT CONNECT ON DATABASE insightpilot TO insight_ro;
GRANT USAGE ON SCHEMA public TO insight_ro;

-- Existing and future tables: read only.
GRANT SELECT ON ALL TABLES IN SCHEMA public TO insight_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO insight_ro;

-- Explicitly withhold everything else.
REVOKE CREATE ON SCHEMA public FROM insight_ro;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM insight_ro;

-- Optional belt and braces: cap runaway analytical queries for this role only.
ALTER ROLE insight_ro SET statement_timeout = '15s';
