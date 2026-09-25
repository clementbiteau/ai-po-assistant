#!/usr/bin/env bash
# Test the Supabase migration + RLS policies on a throwaway PostgreSQL database.
# Usage: DATABASE_URL=postgresql://postgres@127.0.0.1:5432/postgres scripts/test_schema.sh
set -euo pipefail
cd "$(dirname "$0")/.."
: "${DATABASE_URL:?Set DATABASE_URL to an EMPTY, disposable PostgreSQL database (never production)}"
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f supabase/tests/00_supabase_stub.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f supabase/migrations/20260925000000_init.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -q -f supabase/tests/10_rls_test.sql
