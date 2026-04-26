#!/usr/bin/env bash

load_env_file() {
  local candidate="$1"
  if [[ ! -f "${candidate}" ]]; then
    return 1
  fi

  set -a
  # shellcheck disable=SC1090
  source "${candidate}"
  set +a
}

load_project_env() {
  local project_root="$1"
  local base_env_file="${ENV_FILE:-${project_root}/.env}"
  local example_env_file="${project_root}/.env.example"
  local local_env_file="${ENV_LOCAL_FILE:-${project_root}/.env.local}"

  LOADED_ENV_FILE=""
  LOADED_ENV_LOCAL_FILE=""

  if load_env_file "${base_env_file}"; then
    LOADED_ENV_FILE="${base_env_file}"
  elif load_env_file "${example_env_file}"; then
    LOADED_ENV_FILE="${example_env_file}"
  else
    echo "Missing .env or .env.example in ${project_root}" >&2
    return 1
  fi

  if load_env_file "${local_env_file}"; then
    LOADED_ENV_LOCAL_FILE="${local_env_file}"
  fi
}

prepare_runtime_dirs() {
  local project_root="$1"
  local host_data_dir host_backup_dir host_postgres_dir

  host_data_dir="$(resolve_host_path "${project_root}" "${HOST_DATA_DIR:-state/runtime/backend-data}")"
  host_backup_dir="$(resolve_host_path "${project_root}" "${HOST_BACKUP_DIR:-state/runtime/backups}")"
  host_postgres_dir="$(resolve_host_path "${project_root}" "${HOST_POSTGRES_DATA_DIR:-state/runtime/postgres}")"

  mkdir -p \
    "${host_data_dir}" \
    "${host_backup_dir}" \
    "${host_postgres_dir}"

  # The backend container runs as a non-root user, so bind-mounted runtime paths
  # must already be writable on the host before `docker compose up`.
  chmod 0777 \
    "${host_data_dir}" \
    "${host_backup_dir}" \
    "${host_postgres_dir}"
}

resolve_host_path() {
  local project_root="$1"
  local path_value="$2"

  if [[ "${path_value}" = /* ]]; then
    printf '%s\n' "${path_value}"
    return 0
  fi

  printf '%s/%s\n' "${project_root}" "${path_value#./}"
}

export_runtime_paths() {
  local project_root="$1"

  HOST_DATA_DIR="$(resolve_host_path "${project_root}" "${HOST_DATA_DIR:-state/runtime/backend-data}")"
  HOST_BACKUP_DIR="$(resolve_host_path "${project_root}" "${HOST_BACKUP_DIR:-state/runtime/backups}")"
  HOST_POSTGRES_DATA_DIR="$(resolve_host_path "${project_root}" "${HOST_POSTGRES_DATA_DIR:-state/runtime/postgres}")"

  export HOST_DATA_DIR HOST_BACKUP_DIR HOST_POSTGRES_DATA_DIR
}

adopt_legacy_postgres_runtime_dir() {
  local project_root="$1"
  local target_dir="$2"
  local legacy_dir="${project_root}/ops/docker/state/runtime/postgres"
  local timestamp backup_dir

  if [[ ! -f "${legacy_dir}/PG_VERSION" || -f "${target_dir}/PG_VERSION" ]]; then
    return 0
  fi

  if [[ -d "${target_dir}" ]] && find "${target_dir}" -mindepth 1 -maxdepth 1 | read -r _; then
    timestamp="$(date +%Y%m%d%H%M%S)"
    backup_dir="${target_dir}.pre-legacy-migration-${timestamp}"
    mv "${target_dir}" "${backup_dir}"
    echo "Moved incomplete PostgreSQL runtime dir to ${backup_dir}"
  fi

  mkdir -p "${target_dir}"
  cp -a "${legacy_dir}/." "${target_dir}/"
  echo "Adopted legacy PostgreSQL runtime dir from ${legacy_dir}"
}
