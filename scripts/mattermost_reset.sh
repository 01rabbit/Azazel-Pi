#!/usr/bin/env bash
# mattermost_reset.sh
# 完全初期化（DBとアップロード/プラグインを含む）を行います。
# 警告: すべてのユーザー/チーム/チャンネル/投稿/ファイルが失われます。取り返しがつきません。
#
# 対応:
# - systemdで動作するネイティブMattermost (/opt/mattermost)
# - DB: PostgreSQL または SQLite
#   * MySQL は案内メッセージのみ（自動化は最小限）
#
# 使い方:
#   sudo bash scripts/mattermost_reset.sh

set -euo pipefail

if [[ $EUID -ne 0 ]]; then
  echo "[ERROR] rootで実行してください: sudo $0" >&2
  exit 1
fi

# 絶対パス解決（リポジトリルート推定）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

MM_DIR="/opt/mattermost"
CONFIG="${MM_DIR}/config/config.json"
SERVICE_NAME="mattermost"
BACKUP_DIR="/var/backups"
TIMESTAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP_TGZ="${BACKUP_DIR}/mattermost-${TIMESTAMP}.tgz"
COMPOSE_FILE="${REPO_ROOT}/deploy/docker-compose.yml"

if [[ ! -f "$CONFIG" ]]; then
  echo "[ERROR] 設定ファイルが見つかりません: $CONFIG" >&2
  exit 1
fi

confirm() {
  read -r -p "本当にMattermostを完全初期化しますか？(DBやファイルが消えます) 続行するには 'RESET' と入力: " ans
  if [[ "${ans:-}" != "RESET" ]]; then
    echo "[INFO] キャンセルしました。"
    exit 0
  fi
}

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || return 1
}

json_get() {
  # 優先: jq、なければ python3
  local key="$1"
  if need_cmd jq; then
    jq -r "$key" "$CONFIG"
  else
    python3 - "$CONFIG" "$key" <<'PY'
import json, sys
cfg = json.load(open(sys.argv[1]))
# key は .A.B の形
path = sys.argv[2].lstrip('.')
cur = cfg
for k in path.split('.'):
    cur = cur[k]
print(cur)
PY
  fi
}

stop_service() {
  echo "[STEP] サービス停止: ${SERVICE_NAME}"
  if systemctl is-active --quiet "$SERVICE_NAME"; then
    systemctl stop "$SERVICE_NAME"
  fi
}

backup_all() {
  echo "[STEP] バックアップ作成: $BACKUP_TGZ"
  mkdir -p "$BACKUP_DIR"
  tar -C / -czf "$BACKUP_TGZ" opt/mattermost || {
    echo "[WARN] バックアップに失敗しました（続行します）。" >&2
  }
}

reset_sqlite() {
  local dsn="$1"
  # 例: dsn が "/var/lib/mattermost/mattermost.db" のようなパス
  local db_path="${dsn}"
  if [[ -f "$db_path" ]]; then
    echo "[STEP] SQLite DB 削除: $db_path"
    rm -f -- "$db_path"
  else
    echo "[INFO] SQLite DB ファイルが見つかりません: $db_path"
  fi
}

postgres_reset_schema_via_dsn() {
  local dsn="$1"
  echo "[STEP] PostgreSQL フォールバック: スキーマ初期化 (public) を DSN で実行"
  if ! command -v psql >/dev/null 2>&1; then
    echo "[ERROR] psql コマンドが見つかりません。PostgreSQLクライアントをインストールしてください (psql)。" >&2
    return 1
  fi
  # 注意: DSNで mattermost DB に接続し、public スキーマを削除・再作成
  PGPASSWORD="" psql "$dsn" -v ON_ERROR_STOP=1 -c "DROP SCHEMA IF EXISTS public CASCADE; CREATE SCHEMA public;" || {
    echo "[ERROR] DSNユーザーで public スキーマを初期化できませんでした。必要な権限 (CREATE) が無い可能性があります。" >&2
    return 1
  }
}

postgres_drop_create_db() {
  local dsn="$1"
  # DB名: 最後の / と ? の間
  local dbname
  dbname="$(echo "$dsn" | sed -E 's|.*/([^/?]+).*|\1|')"
  if [[ -z "$dbname" || "$dbname" == "$dsn" ]]; then
    echo "[ERROR] DB名の抽出に失敗しました。DSN=$dsn" >&2
    return 1
  fi
  echo "[STEP] PostgreSQL データベース初期化: $dbname"

  # まずはローカル管理ユーザー (postgres) でDB再作成を試行
  if id postgres >/dev/null 2>&1 && sudo -n -u postgres psql -V >/dev/null 2>&1; then
    # 接続中セッションを切断 → DROP → CREATE
    sudo -n -u postgres psql -v ON_ERROR_STOP=1 -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${dbname}';" || true
    sudo -n -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS \"${dbname}\";" || {
      echo "[WARN] DROP DATABASE に失敗。フォールバックに切り替えます。" >&2
      postgres_reset_schema_via_dsn "$dsn"
      return $?
    }
    sudo -n -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE \"${dbname}\";" || {
      echo "[WARN] CREATE DATABASE に失敗。フォールバックに切り替えます。" >&2
      postgres_reset_schema_via_dsn "$dsn"
      return $?
    }
  else
    echo "[INFO] 'postgres' ユーザー/権限が利用できません。フォールバックでスキーマ初期化を試みます。"
    postgres_reset_schema_via_dsn "$dsn"
    return $?
  fi
}

reset_mysql_hint() {
  local dsn="$1"
  echo "[INFO] MySQL/MariaDB を使用しているようです。自動化は行いません。以下を参考に手動で実行してください:"
  cat <<"EOS"
# 例: rootで実行（パスワードが必要な場合あり）
mysql -u root -p -e "DROP DATABASE IF EXISTS mattermost; CREATE DATABASE mattermost CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;"
# DSNのDB名が 'mattermost' でない場合は適宜置換してください。
EOS
}

wipe_files() {
  echo "[STEP] アップロード/プラグインの削除"
  local paths=(
    "${MM_DIR}/data"
    "${MM_DIR}/plugins"
    "${MM_DIR}/client/plugins"
    "${MM_DIR}/logs"
  )
  for p in "${paths[@]}"; do
    if [[ -d "$p" ]]; then
      echo "  - $p を空にします"
      find "$p" -mindepth 1 -maxdepth 1 -exec rm -rf {} + || true
    fi
  done
}

start_service() {
  echo "[STEP] サービス起動: ${SERVICE_NAME}"
  systemctl start "$SERVICE_NAME"
  sleep 2
  systemctl --no-pager --full status "$SERVICE_NAME" || true
}

# ------------------------------
# Docker(PostgreSQL) サポート
# ------------------------------
docker_compose_cmd() {
  if command -v docker >/dev/null 2>&1 && docker compose version >/dev/null 2>&1; then
    echo "docker compose"
    return 0
  elif command -v docker-compose >/dev/null 2>&1; then
    echo "docker-compose"
    return 0
  fi
  return 1
}

is_docker_postgres() {
  # 1) composeファイルに postgres サービスがある 2) コンテナが存在/データディレクトリがある
  [[ -f "$COMPOSE_FILE" ]] || return 1
  grep -q "^\s*postgres:\s*$" "$COMPOSE_FILE" || return 1
  # どちらか満たせばDocker運用と判断
  docker ps -a --format '{{.Names}}' 2>/dev/null | grep -q '^azazel_postgres$' && return 0
  [[ -d "/opt/azazel/data/postgres" ]] && return 0
  return 0  # composeに定義があればDocker前提で進める
}

parse_pg_user_from_dsn() {
  # 例: postgres://user:pass@host:5432/db?...
  local dsn="$1"
  echo "$dsn" | sed -E 's|^[^:]+://([^:]+):.*|\1|' 2>/dev/null || true
}

docker_postgres_reset() {
  local dsn="$1"
  local dc
  if ! dc="$(docker_compose_cmd)"; then
    echo "[ERROR] docker compose/docker-compose が見つかりません。Docker環境を確認してください。" >&2
    return 1
  fi

  echo "[STEP] Docker PostgreSQL を初期化 (compose: $COMPOSE_FILE)"
  # Mattermost停止済み前提
  (cd "$REPO_ROOT/deploy" && $dc -f "$COMPOSE_FILE" down) || true

  # データディレクトリをバックアップして消去
  local pg_data="/opt/azazel/data/postgres"
  if [[ -d "$pg_data" ]]; then
    echo "  - PostgreSQLデータをバックアップ: ${BACKUP_DIR}/pgdata-${TIMESTAMP}.tgz"
    mkdir -p "$BACKUP_DIR"
    tar -C / -czf "${BACKUP_DIR}/pgdata-${TIMESTAMP}.tgz" opt/azazel/data/postgres || true
    echo "  - PostgreSQLデータを消去: $pg_data"
    find "$pg_data" -mindepth 1 -maxdepth 1 -exec rm -rf {} + || true
  else
    echo "  - データディレクトリが見つかりませんでした（初回起動の可能性）: $pg_data"
  fi

  echo "  - コンテナ起動(PostgreSQL)"
  (cd "$REPO_ROOT/deploy" && $dc -f "$COMPOSE_FILE" up -d postgres)

  # 起動待ち合わせ
  local user dbname
  user="$(parse_pg_user_from_dsn "$dsn")"
  dbname="$(echo "$dsn" | sed -E 's|.*/([^/?]+).*|\1|')"
  local max_wait=60 i=0
  echo "  - 起動確認 (pg_isready) user=${user:-mmuser} db=${dbname:-mattermost}"
  while (( i < max_wait )); do
    if docker exec azazel_postgres pg_isready -U "${user:-mmuser}" -d "${dbname:-mattermost}" >/dev/null 2>&1; then
      echo "  - PostgreSQL が起動しました"
      break
    fi
    sleep 1; ((i++))
  done
  if (( i >= max_wait )); then
    echo "[WARN] PostgreSQL の起動確認に失敗しましたが続行します。ログ: docker logs azazel_postgres を確認してください。" >&2
  fi
}

main() {
  echo "[INFO] Mattermost 完全初期化を開始"
  confirm

  stop_service
  backup_all

  local driver dsn
  driver="$(json_get '.SqlSettings.DriverName' || true)"
  dsn="$(json_get '.SqlSettings.DataSource' || true)"

  echo "[INFO] DriverName: ${driver:-unknown}"
  echo "[INFO] DataSource: ${dsn:-empty}"

  case "${driver}" in
    postgres|"postgres")
      if is_docker_postgres; then
        docker_postgres_reset "$dsn"
      else
        postgres_drop_create_db "$dsn"
      fi
      ;;
    mysql|"mysql")
      reset_mysql_hint "$dsn"
      ;;
    sqlite3|"sqlite3")
      reset_sqlite "$dsn"
      ;;
    *)
      # DSNから推定（postgres://, postgresql://, mysql://, *.db）
      if [[ "${dsn}" =~ ^postgres(|ql):// ]]; then
        postgres_drop_create_db "$dsn"
      elif [[ "${dsn}" =~ ^mysql:// ]] || [[ "${dsn}" =~ @tcp\( ]]; then
        reset_mysql_hint "$dsn"
      elif [[ "${dsn}" == *.db ]] || [[ "${dsn}" == /*.db ]]; then
        reset_sqlite "$dsn"
      else
        echo "[ERROR] DB種別を判定できませんでした。config.json を確認してください。" >&2
        exit 1
      fi
      ;;
  esac

  wipe_files
  start_service

  echo "[DONE] 初期化が完了しました。"
  cat <<EOF
次の手順:
- ブラウザで http://<この端末のIP>/ にアクセス
- 最初のユーザーを作成（通常は最初のユーザーがSystem Adminになります）
- サインアップが制限されている場合は ${CONFIG} の設定を見直してください（必要なら一時的に "ServiceSettings" → "EnableOpenServer": true など）。
- Nginxを使っている場合は既にリバースプロキシが有効です（scripts/setup_nginx_mattermost.sh 参照）。
バックアップ: ${BACKUP_TGZ}
EOF
}

main "$@"
