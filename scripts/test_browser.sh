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
  printf 'Cárgalas desde .env.test; nunca se conectará a la base de desarrollo.\n' >&2
  exit 2
fi

export DJANGO_SETTINGS_MODULE=config.settings_test
exec .venv/bin/python manage.py test talento.test_playwright --verbosity 2
