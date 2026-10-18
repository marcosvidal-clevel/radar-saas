#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_vars=(RADAR_TEST_DB_NAME RADAR_TEST_DB_USER RADAR_TEST_DB_PASSWORD)
missing_vars=()
for variable in "${required_vars[@]}"; do
  if [[ -z "${!variable:-}" ]]; then
    missing_vars+=("$variable")
  fi
done

if ((${#missing_vars[@]} > 0)); then
  printf 'Faltan variables obligatorias: %s\n' "${missing_vars[*]}" >&2
  printf 'Configúralas en .env.test (usa .env.test.example como plantilla) y carga el archivo así:\n' >&2
  printf '  set -a; source .env.test; set +a\n' >&2
  printf 'Luego vuelve a ejecutar: ./scripts/test_suite.sh\n' >&2
  exit 2
fi

export DJANGO_SETTINGS_MODULE=config.settings_test
exec .venv/bin/python manage.py test config core talento --verbosity 2
