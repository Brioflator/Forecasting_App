-- A dedicated test database for the DB-touching pytest suites (plan 05 §2.6):
-- migrated once per session, truncated between tests, never testcontainers.
CREATE DATABASE forecast_test OWNER forecast;
