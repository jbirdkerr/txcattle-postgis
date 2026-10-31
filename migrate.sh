#!/usr/bin/env bash
# Apply numbered migrations in order. Each file runs once; applied files are
# recorded in schema_migrations. Stops on the first error.
#
# Default: runs psql inside the docker compose container.
# Set USE_LOCAL_PSQL=1 to run a local psql against the same database instead.
set -euo pipefail

CONTAINER="${CONTAINER:-txcattle-db}"
DB_USER="${DB_USER:-txcattle}"
DB_NAME="${DB_NAME:-txcattle}"

psql_run() {
  if [[ "${USE_LOCAL_PSQL:-0}" == "1" ]]; then
    psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"
  else
    docker exec -i "$CONTAINER" psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" "$@"
  fi
}

psql_run -q <<'SQL'
CREATE TABLE IF NOT EXISTS schema_migrations (
  filename   text PRIMARY KEY,
  applied_at timestamptz NOT NULL DEFAULT now()
);
SQL

for f in migrations/*.sql; do
  name="$(basename "$f")"
  already="$(psql_run -tA -c "SELECT 1 FROM schema_migrations WHERE filename = '$name';")"
  if [[ "$already" == "1" ]]; then
    echo "skip   $name (already applied)"
    continue
  fi
  echo "apply  $name"
  psql_run -q < "$f"
  psql_run -q -c "INSERT INTO schema_migrations (filename) VALUES ('$name');"
done

echo "All migrations applied."
