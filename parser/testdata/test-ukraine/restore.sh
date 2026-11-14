#!/usr/bin/env bash
# Deploys a FIRMS dump package into the firms schema of PostgreSQL 17+ with PostGIS 3.
#
#   ./restore.sh [--jobs N] [--only-year YYYY]
#
# It reads the package from its own folder. The connection comes from the libpq variables PGHOST, PGPORT,
# PGUSER, PGPASSWORD and PGDATABASE. No superuser is needed: the user must be able to create a schema in the
# database, and PostGIS must be installed in it already unless the user may install it. The data goes through
# psql's \copy ... FROM PROGRAM, which runs gzip where this script runs; that machine needs bash, psql and gzip.
#
# Steps:
#   1. check the server: PostgreSQL 17 or newer, PostGIS 3;
#   2. run schema/*.sql (the indexes wait for step 6) and record the files in firms.schema_migrations;
#   3. create the parts of firms.hotspot and firms.hotspot_static that manifest.json names;
#   4. load each data file in a transaction of its own that first empties what the file replaces, N at a time;
#   5. fill firms.grid_cell when it is empty;
#   6. build the indexes (schema/03_indexes.sql) and ANALYZE;
#   7. rebuild the series of every method version in the database (firms.build_series);
#   8. compare the row counts with manifest.json;
#   9. record the package in firms.dataset;
#  10. journal the run in public.ingest_runs when the application has that table: a row per source, running from
#      step 2 on, then success or failed.
# It prints OK at the end, or the counts that differ and exits with 1.
#
# --jobs N          files loaded at the same time (default 4).
# --only-year YYYY  reload only the parts of that year (hotspot_YYYY_*, hotspot_static_YYYY), replace that year's
#                   days in firms.day_source, add or update the package's rows of firms.load_batch, and rebuild
#                   the series of that year's months. The other tables keep their rows.
#
# Running it again is safe: each file replaces the rows it carries, and a file that fails leaves the old rows in
# place. Do not run two restores on one database at the same time.

set -euo pipefail

SELF=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")
PKG_DIR=$(dirname "$SELF")
INDEX_FILE=schema/03_indexes.sql
PSQL=(psql -X -q -v ON_ERROR_STOP=1)
export PGOPTIONS="${PGOPTIONS:-} -c client_min_messages=warning"
STEP=""
RUN_IDS=""
RUN_SOURCES=""
LOADED_BATCHES=""

die() {
    printf 'restore.sh: %s\n' "$*" >&2
    exit 1
}

say() {
    printf '%s\n' "$*"
}

step() {
    STEP=$1
    printf '== %s (%s)\n' "$1" "$(date +%T)"
}

usage() {
    sed -n '2,/^$/{s/^# \{0,1\}//;p;}' "$SELF"
}

# Runs SQL in which :'manifest' is the text of manifest.json; prints the rows with fields separated by |.
# psql reads the file itself (the backticks are psql's), so its size does not meet the limit of a command line.
manifest_sql() {
    # shellcheck disable=SC2016
    { printf '%s\n' '\set manifest `cat manifest.json`'; printf '%s\n' "$1"; } |
        "${PSQL[@]}" -A -t -F '|' -f -
}

file_sha256() {
    if command -v sha256sum >/dev/null; then
        sha256sum "$1" | cut -d ' ' -f 1
    else
        shasum -a 256 "$1" | cut -d ' ' -f 1
    fi
}

record_migrations() {
    local file values=""
    for file in "$@"; do
        values+="${values:+, }('$(basename "$file")', '$(file_sha256 "$file")', now())"
    done
    if [[ -n $values ]]; then
        "${PSQL[@]}" -c "INSERT INTO firms.schema_migrations (file, sha256, applied_at) VALUES $values
                         ON CONFLICT (file) DO UPDATE SET sha256 = EXCLUDED.sha256, applied_at = EXCLUDED.applied_at"
    fi
}

# One load job, run by xargs in a process of its own: KIND|TABLE|ARGUMENT|FILE[,FILE...]
#   replace  empty the table or part, then copy the files into it;
#   version  delete the rows of method version ARGUMENT, then copy the files (none: the version has no such rows);
#   days     replace the days of year ARGUMENT in day_source with those of the file;
#   batches  add the rows of the file to load_batch, replacing the rows with the same id.
load_job() {
    local kind table arg files file next
    local -a list=() cmds=()
    IFS='|' read -r kind table arg files <<<"$1"
    IFS=',' read -r -a list <<<"$files"
    case $kind in
        replace)
            cmds+=(-c "TRUNCATE firms.$table")
            for file in "${list[@]}"; do
                cmds+=(-c "\\copy firms.$table FROM PROGRAM 'gzip -dc $file'")
            done
            ;;
        version)
            cmds+=(-c "DELETE FROM firms.$table WHERE version = '$arg'")
            for file in "${list[@]}"; do
                cmds+=(-c "\\copy firms.$table FROM PROGRAM 'gzip -dc $file'")
            done
            ;;
        days)
            next=$((10#$arg + 1))
            cmds+=(-c "CREATE TEMP TABLE incoming (LIKE firms.day_source) ON COMMIT DROP"
                   -c "\\copy incoming FROM PROGRAM 'gzip -dc ${list[0]}'"
                   -c "DELETE FROM firms.day_source WHERE day >= DATE '$arg-01-01' AND day < DATE '$next-01-01'"
                   -c "INSERT INTO firms.day_source SELECT * FROM incoming
                       WHERE day >= DATE '$arg-01-01' AND day < DATE '$next-01-01'")
            ;;
        batches)
            cmds+=(-c "CREATE TEMP TABLE incoming (LIKE firms.load_batch) ON COMMIT DROP"
                   -c "\\copy incoming FROM PROGRAM 'gzip -dc ${list[0]}'"
                   -c "INSERT INTO firms.load_batch SELECT * FROM incoming ON CONFLICT (id) DO UPDATE SET
                       source_code = EXCLUDED.source_code, is_nrt = EXCLUDED.is_nrt, file = EXCLUDED.file,
                       member_count = EXCLUDED.member_count, file_size = EXCLUDED.file_size,
                       file_mtime = EXCLUDED.file_mtime, versions = EXCLUDED.versions,
                       date_from = EXCLUDED.date_from, date_to = EXCLUDED.date_to,
                       rows_fire = EXCLUDED.rows_fire, rows_static = EXCLUDED.rows_static")
            ;;
        *)
            die "unknown load job: $1"
            ;;
    esac
    "${PSQL[@]}" -1 "${cmds[@]}"
    say "  loaded $table${arg:+ $arg}"
}

# Journal rows of the application: one per source of the loaded files with the period of its files, running until
# the run ends. RUN_IDS lists the rows; RUN_SOURCES pairs each with its source for the count at the end.
start_runs() {
    local only_year=$1 started=$2 tables batch_file="" i source_id="NULL::bigint" where="true" runs id code
    tables=$("${PSQL[@]}" -A -t -F '|' -c "SELECT to_regclass('public.ingest_runs') IS NOT NULL,
                                                  to_regclass('public.data_sources') IS NOT NULL")
    if [[ ${tables%%|*} != t ]]; then
        return 0
    fi
    for i in "${!E_TABLE[@]}"; do
        if [[ ${E_TABLE[i]} == load_batch ]]; then
            batch_file=${E_FILE[i]}
        fi
    done
    if [[ -z $batch_file ]]; then
        return 0
    fi
    if [[ ${tables#*|} == t ]]; then
        source_id="(SELECT d.id FROM public.data_sources d WHERE d.code = s.source_code)"
    fi
    if [[ -n $only_year ]]; then
        where="b.date_from <= DATE '$only_year-12-31' AND b.date_to >= DATE '$only_year-01-01'"
    fi
    # The ids come from the table's sequence first, so each row is known with its source. The journal is the
    # application's: when its table does not take the rows, the data still goes in.
    if ! runs=$("${PSQL[@]}" -A -t -F '|' -1 \
        -c "CREATE TEMP TABLE incoming (LIKE firms.load_batch) ON COMMIT DROP" \
        -c "\\copy incoming FROM PROGRAM 'gzip -dc $batch_file'" \
        -c "WITH s AS (
                SELECT nextval(pg_get_serial_sequence('public.ingest_runs', 'id')) AS id, x.*
                FROM (SELECT b.source_code, min(b.date_from) AS date_from, max(b.date_to) AS date_to
                      FROM incoming b WHERE $where GROUP BY b.source_code ORDER BY b.source_code) AS x
            ), runs AS (
                INSERT INTO public.ingest_runs (id, data_source_id, period_from, period_to, status, records_count,
                                                started_at, created_at, updated_at)
                SELECT s.id, $source_id, s.date_from, s.date_to, 'running', 0,
                       TIMESTAMP '$started', now() AT TIME ZONE 'UTC', now() AT TIME ZONE 'UTC'
                FROM s
                RETURNING id)
            SELECT s.id, s.source_code FROM s JOIN runs USING (id) ORDER BY s.id"); then
        printf 'restore.sh: warning: public.ingest_runs did not take the journal rows; going on without them\n' >&2
        RUN_IDS="" RUN_SOURCES=""
        return 0
    fi
    RUN_IDS="" RUN_SOURCES=""
    while IFS='|' read -r id code; do
        if [[ $id =~ ^[0-9]+$ ]]; then
            [[ $code =~ ^[A-Za-z0-9_]+$ ]] || code=""  # an odd code is never quoted into SQL; it counts 0
            RUN_IDS+="${RUN_IDS:+,}$id"
            RUN_SOURCES+="${RUN_SOURCES:+, }($id, '$code')"
        fi
    done <<<"$runs"
}

# The journal at the end. success takes the rows loaded from each source, fires and non-fires, from the counts
# by batch that step 8 made of every part this run loaded (LOADED_BATCHES); failed keeps 0 and writes the reason.
# A success the table does not take becomes failed with that reason rather than staying running.
finish_runs() {
    local status=$1 error=${2-} sql failure
    if [[ -z $RUN_IDS ]]; then
        return 0
    fi
    if [[ $status == success ]]; then
        sql="WITH loaded (batch_id, n) AS (${LOADED_BATCHES:-SELECT NULL::integer, NULL::bigint WHERE false}),
             per_source AS (
                 SELECT b.source_code, sum(l.n) AS n FROM loaded l JOIN firms.load_batch b ON b.id = l.batch_id
                 GROUP BY b.source_code
             )
             UPDATE public.ingest_runs r SET status = 'success', records_count = coalesce(ps.n, 0),
                    finished_at = now() AT TIME ZONE 'UTC', updated_at = now() AT TIME ZONE 'UTC'
             FROM (VALUES $RUN_SOURCES) AS v(id, code) LEFT JOIN per_source ps ON ps.source_code = v.code
             WHERE r.id = v.id;"
        if failure=$(printf '%s\n' "$sql" | "${PSQL[@]}" -f - 2>&1); then
            RUN_IDS="" RUN_SOURCES=""
            return 0
        fi
        status=failed
        error="the data is in and checked, but public.ingest_runs did not take the counts: $failure"
        printf 'restore.sh: warning: %s\n' "$error" >&2
    fi
    sql="UPDATE public.ingest_runs SET status = :'status', error = nullif(:'error', ''),
                finished_at = now() AT TIME ZONE 'UTC', updated_at = now() AT TIME ZONE 'UTC'
         WHERE id IN ($RUN_IDS);"
    if ! printf '%s\n' "$sql" | "${PSQL[@]}" -v status="$status" -v error="$error" -f -; then
        printf 'restore.sh: warning: could not mark the journal rows %s as %s\n' "$RUN_IDS" "$status" >&2
    fi
    RUN_IDS="" RUN_SOURCES=""
}

on_exit() {
    if (($1 != 0)) && [[ -n $RUN_IDS ]]; then
        finish_runs failed "restore.sh stopped at step $STEP" || true
    fi
}

main() {
    local jobs=4 only_year="" i t part year sat ver file rows started
    started=$(date -u '+%Y-%m-%d %H:%M:%S')
    while (($#)); do
        case $1 in
            --jobs) (($# >= 2)) || die "--jobs needs a number"; jobs=$2; shift 2 ;;
            --jobs=*) jobs=${1#*=}; shift ;;
            --only-year) (($# >= 2)) || die "--only-year needs a year"; only_year=$2; shift 2 ;;
            --only-year=*) only_year=${1#*=}; shift ;;
            -h | --help) usage; exit 0 ;;
            *) die "unknown argument: $1 (see --help)" ;;
        esac
    done
    [[ $jobs =~ ^[1-9][0-9]*$ ]] || die "--jobs needs a positive number, not '$jobs'"
    [[ -z $only_year || $only_year =~ ^[0-9]{4}$ ]] || die "--only-year needs a year like 2026, not '$only_year'"

    cd "$PKG_DIR"
    command -v psql >/dev/null || die "psql is not installed"
    command -v gzip >/dev/null || die "gzip is not installed"
    [[ -f manifest.json ]] || die "there is no manifest.json in $PKG_DIR"

    step "1. server"
    local server pg_version pg_name postgis available superuser
    server=$("${PSQL[@]}" -A -t -F '|' -c "SELECT current_setting('server_version_num'),
            current_setting('server_version'),
            coalesce((SELECT extversion FROM pg_extension WHERE extname = 'postgis'), ''),
            coalesce((SELECT default_version FROM pg_available_extensions WHERE name = 'postgis'), ''),
            (SELECT rolsuper FROM pg_roles WHERE rolname = current_user)") ||
        die "cannot connect to the database: check PGHOST, PGPORT, PGUSER, PGPASSWORD and PGDATABASE"
    IFS='|' read -r pg_version pg_name postgis available superuser <<<"$server"
    ((pg_version >= 170000)) || die "the server runs PostgreSQL $pg_name; PostgreSQL 17 or newer is needed"
    if [[ -n $postgis ]]; then
        [[ $postgis == 3.* ]] || die "the database has PostGIS $postgis; PostGIS 3 is needed"
    elif [[ -z $available ]]; then
        die "PostGIS is not installed on the server"
    elif [[ $superuser != t ]]; then
        die "PostGIS $available is not installed in this database: a superuser must run CREATE EXTENSION postgis there once"
    fi
    say "PostgreSQL $pg_name, PostGIS ${postgis:-$available}"

    # The files of the package. Every value that reaches SQL or a shell command is checked here.
    local name entries
    name=$(manifest_sql "SELECT coalesce(:'manifest'::jsonb ->> 'name', '')") || die "manifest.json cannot be read"
    [[ -n $name ]] || die "manifest.json has no name"
    entries=$(manifest_sql "SELECT f ->> 'table', coalesce(f ->> 'partition', ''), coalesce(f ->> 'year', ''),
                                   coalesce(f ->> 'satellite', ''), coalesce(f ->> 'version', ''),
                                   coalesce(f ->> 'file', ''), coalesce(f ->> 'rows', '')
                            FROM jsonb_array_elements(:'manifest'::jsonb -> 'files') AS f")
    E_TABLE=() E_PART=() E_YEAR=() E_SAT=() E_VERSION=() E_FILE=() E_ROWS=()
    while IFS='|' read -r t part year sat ver file rows; do
        if [[ -n $t ]]; then
            E_TABLE+=("$t") E_PART+=("$part") E_YEAR+=("$year") E_SAT+=("$sat") E_VERSION+=("$ver")
            E_FILE+=("$file") E_ROWS+=("$rows")
        fi
    done <<<"$entries"
    ((${#E_TABLE[@]})) || die "manifest.json lists no files"

    declare -A sat_id=()
    local satellite_file="" satellites id code
    for i in "${!E_TABLE[@]}"; do
        if [[ ${E_TABLE[i]} == satellite ]]; then
            satellite_file=${E_FILE[i]}
        fi
    done
    [[ -n $satellite_file ]] || die "manifest.json lists no satellite file"
    [[ $satellite_file =~ ^data/[A-Za-z0-9_][A-Za-z0-9_./-]*\.tsv\.gz$ && -f $satellite_file ]] ||
        die "the satellite file $satellite_file is not in the package"
    satellites=$(gzip -dc "$satellite_file") || die "cannot read $satellite_file"
    while IFS=$'\t' read -r id code _; do
        if [[ $id =~ ^[0-9]+$ && $code =~ ^[a-z0-9]+$ ]]; then
            sat_id[$code]=$id
        fi
    done <<<"$satellites"

    local -a selected=()
    declare -A carried=()  # method versions a full run loads: each one replaces that version as a whole
    declare -A package_versions=()  # method versions in the package: their series must build
    for i in "${!E_TABLE[@]}"; do
        t=${E_TABLE[i]} part=${E_PART[i]} year=${E_YEAR[i]} sat=${E_SAT[i]} ver=${E_VERSION[i]}
        file=${E_FILE[i]} rows=${E_ROWS[i]}
        [[ $file =~ ^data/[A-Za-z0-9_][A-Za-z0-9_./-]*\.tsv\.gz$ && $file != *..* ]] ||
            die "manifest.json: bad file name '$file'"
        [[ -f $file ]] || die "manifest.json lists $file, which is not in the package"
        [[ $rows =~ ^[0-9]+$ ]] || die "manifest.json gives no row count for $file"
        case $t in
            hotspot)
                [[ $year =~ ^[0-9]{4}$ && -n $sat && -n ${sat_id[$sat]-} && $part == "hotspot_${year}_$sat" ]] ||
                    die "manifest.json: $file needs a year, a satellite of $satellite_file and the part hotspot_<year>_<satellite>"
                ;;
            hotspot_static)
                [[ $year =~ ^[0-9]{4}$ && $part == "hotspot_static_$year" ]] ||
                    die "manifest.json: $file needs a year and the part hotspot_static_<year>"
                ;;
            satellite | load_batch | day_source | archive_cell) ;;
            method | method_weight | method_factor | method_error | method_gap)
                [[ $ver =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] || die "manifest.json: bad method version '$ver' of $file"
                package_versions[$ver]=1
                if [[ -z $only_year ]]; then
                    carried[$ver]=${carried[$ver]-}
                    if [[ $t == method ]]; then
                        carried[$ver]=1
                    fi
                fi
                ;;
            *) die "manifest.json: unknown table '$t' of $file" ;;
        esac
        if [[ -z $only_year ]]; then
            selected+=("$i")
        elif [[ ($t == hotspot || $t == hotspot_static) && $year == "$only_year" ]] ||
            [[ $t == day_source || $t == load_batch ]]; then
            selected+=("$i")
        fi
    done
    for ver in "${!carried[@]}"; do
        [[ -n ${carried[$ver]} ]] || die "manifest.json carries method version $ver without its method file"
    done
    if [[ -n $only_year ]]; then
        local has_year=""
        for i in "${selected[@]}"; do
            if [[ ${E_TABLE[i]} == hotspot || ${E_TABLE[i]} == hotspot_static ]]; then
                has_year=1
            fi
        done
        [[ -n $has_year ]] || die "the package has no files of $only_year"
    fi

    step "2. schema"
    shopt -s nullglob
    local -a schema_files=(schema/*.sql) applied=()
    ((${#schema_files[@]})) || die "there is no schema/*.sql in the package"
    # CREATE TABLE IF NOT EXISTS leaves existing tables as they are, so changed tables would fail at \copy later.
    local recorded=""
    if [[ -f schema/01_tables.sql &&
        $("${PSQL[@]}" -A -t -c "SELECT to_regclass('firms.schema_migrations') IS NOT NULL") == t ]]; then
        recorded=$("${PSQL[@]}" -A -t -c "SELECT sha256 FROM firms.schema_migrations WHERE file = '01_tables.sql'")
    fi
    if [[ -n $recorded && $recorded != "$(file_sha256 schema/01_tables.sql)" ]]; then
        die "schema/01_tables.sql differs from the file the tables of this database were made with (sha256 $recorded
in firms.schema_migrations), and its CREATE TABLE IF NOT EXISTS does not change existing tables. Change the tables
to match the new file and delete the row of 01_tables.sql from firms.schema_migrations, or drop the schema firms
and restore again."
    fi
    for file in "${schema_files[@]}"; do
        [[ $file =~ ^schema/[A-Za-z0-9_.-]+\.sql$ ]] || die "bad schema file name $file"
        if [[ $file != "$INDEX_FILE" ]]; then
            "${PSQL[@]}" -1 -f "$file"
            applied+=("$file")
        fi
    done
    record_migrations "${applied[@]}"
    if [[ -n $only_year ]]; then
        # A run of one year loads no method tables, so it can build only versions that are already there.
        declare -A in_database=()
        while IFS= read -r ver; do
            in_database[$ver]=1
        done < <("${PSQL[@]}" -A -t -c "SELECT version FROM firms.method")
        for ver in "${!package_versions[@]}"; do
            [[ -n ${in_database[$ver]-} ]] || die "version $ver is not in the database; run a full restore"
        done
    fi
    trap 'on_exit $?' EXIT
    start_runs "$only_year" "$started"

    step "3. parts"
    local -a ddl=()
    local next
    for i in "${selected[@]}"; do
        year=${E_YEAR[i]}
        if [[ ${E_TABLE[i]} == hotspot || ${E_TABLE[i]} == hotspot_static ]]; then
            next=$((10#$year + 1))
        fi
        case ${E_TABLE[i]} in
            hotspot)
                ddl+=("CREATE TABLE IF NOT EXISTS firms.hotspot_$year PARTITION OF firms.hotspot
                           FOR VALUES FROM ('$year-01-01') TO ('$next-01-01') PARTITION BY LIST (satellite);"
                      "CREATE TABLE IF NOT EXISTS firms.${E_PART[i]} PARTITION OF firms.hotspot_$year
                           FOR VALUES IN (${sat_id[${E_SAT[i]}]});")
                ;;
            hotspot_static)
                ddl+=("CREATE TABLE IF NOT EXISTS firms.${E_PART[i]} PARTITION OF firms.hotspot_static
                           FOR VALUES FROM ('$year-01-01') TO ('$next-01-01');")
                ;;
        esac
    done
    if ((${#ddl[@]})); then
        printf '%s\n' "${ddl[@]}" | "${PSQL[@]}" -1 -f -
    fi

    step "4. data, $jobs files at a time"
    local -a load_jobs=()
    declare -A part_files=() version_files=()
    for i in "${selected[@]}"; do
        t=${E_TABLE[i]} file=${E_FILE[i]}
        case $t in
            # A part gets all its files in one job that empties it once: a part of hotspot_static has a file per
            # family of satellites.
            hotspot | hotspot_static) part_files[${E_PART[i]}]+="${part_files[${E_PART[i]}]:+,}$file" ;;
            load_batch | day_source)
                if [[ -z $only_year ]]; then
                    load_jobs+=("replace|$t||$file")
                elif [[ $t == load_batch ]]; then
                    load_jobs+=("batches|$t||$file")
                else
                    load_jobs+=("days|$t|$only_year|$file")
                fi
                ;;
            satellite | archive_cell) load_jobs+=("replace|$t||$file") ;;
            *) version_files["$t ${E_VERSION[i]}"]+="${version_files["$t ${E_VERSION[i]}"]:+,}$file" ;;
        esac
    done
    for part in "${!part_files[@]}"; do
        load_jobs+=("replace|$part||${part_files[$part]}")
    done
    local -a emptied=()
    if [[ -n $only_year ]]; then
        # The package replaces the whole year: a part of it that the package lacks would keep old rows.
        local leaf leaves
        leaves=$("${PSQL[@]}" -A -t -c "SELECT c.relname FROM pg_partition_tree('firms.hotspot') AS p
                                        JOIN pg_class c ON c.oid = p.relid
                                        WHERE p.isleaf AND p.parentrelid = to_regclass('firms.hotspot_$only_year')
                                        UNION ALL
                                        SELECT c.relname FROM pg_class c
                                        WHERE c.oid = to_regclass('firms.hotspot_static_$only_year')")
        while IFS= read -r leaf; do
            if [[ -n $leaf && -z ${part_files[$leaf]+set} ]]; then
                [[ $leaf =~ ^[a-z0-9_]+$ ]] || die "the part firms.$leaf of $only_year has a name restore.sh does not use"
                load_jobs+=("replace|$leaf||")
                emptied+=("$leaf")
                say "  emptied $leaf: the package has no file of it"
            fi
        done <<<"$leaves"
    fi
    # A version the package carries loses its old rows in all five tables, also where it brings no file.
    for ver in "${!carried[@]}"; do
        for t in method method_weight method_factor method_error method_gap; do
            load_jobs+=("version|$t|$ver|${version_files["$t $ver"]-}")
        done
    done
    printf '%s\0' "${load_jobs[@]}" | xargs -0 -n 1 -P "$jobs" "$BASH" "$SELF" __load ||
        die "loading failed; a file that failed left its table as it was, see the errors above"

    step "5. grid"
    "${PSQL[@]}" -c "INSERT INTO firms.grid_cell (cell_id, geom)
                     SELECT c, firms.cell_geom(c) FROM generate_series(0, 1036799) AS c
                     WHERE NOT EXISTS (SELECT 1 FROM firms.grid_cell)"

    step "6. indexes"
    if [[ -f $INDEX_FILE ]]; then
        "${PSQL[@]}" -1 -f "$INDEX_FILE"
        record_migrations "$INDEX_FILE"
    fi
    "${PSQL[@]}" -c "ANALYZE firms.satellite, firms.load_batch, firms.day_source, firms.archive_cell, firms.hotspot,
                             firms.hotspot_static, firms.method, firms.method_weight, firms.method_factor,
                             firms.method_error, firms.method_gap, firms.grid_cell"

    step "7. series"
    local versions version build failure
    if [[ -n $only_year ]]; then
        build="SELECT firms.build_series(:'v', DATE '$only_year-01-01', DATE '$only_year-12-01');"
    else
        build="SELECT firms.build_series(:'v');"
    fi
    versions=$("${PSQL[@]}" -A -t -c "SELECT version FROM firms.method ORDER BY version")
    while IFS= read -r version; do
        if [[ -z $version ]]; then
            continue
        fi
        if [[ -n ${package_versions[$version]-} ]]; then
            printf '%s\n' "$build" | "${PSQL[@]}" -A -t -v v="$version" -f - >/dev/null
            say "  built the series of $version"
        # A version of an earlier package reads the new fires too, but its failure does not stop this package.
        elif failure=$(printf '%s\n' "$build" | "${PSQL[@]}" -A -t -v v="$version" -f - 2>&1 >/dev/null); then
            say "  built the series of $version, which the package does not carry"
        else
            printf 'restore.sh: warning: the series of %s, which the package does not carry, was not rebuilt and keeps the sums of the earlier data: %s\n' \
                "$version" "$failure" >&2
        fi
    done <<<"$versions"
    "${PSQL[@]}" -c "ANALYZE firms.cell_month_series, firms.method_month"

    step "8. row counts"
    declare -A expected=() unlisted=()
    local key leaves leaf
    for i in "${selected[@]}"; do
        t=${E_TABLE[i]}
        case $t in
            hotspot | hotspot_static) key=${E_PART[i]} ;;
            method*) key="$t ${E_VERSION[i]}" ;;
            *) key=$t ;;
        esac
        # In a run of one year, day_source and load_batch also hold the other years.
        if [[ -z $only_year || $t == hotspot || $t == hotspot_static ]]; then
            expected[$key]=$((${expected[$key]:-0} + 10#${E_ROWS[i]}))
        fi
    done
    for ver in "${!carried[@]}"; do
        for t in method method_weight method_factor method_error method_gap; do
            expected["$t $ver"]=${expected["$t $ver"]:-0}
        done
    done
    for leaf in "${emptied[@]}"; do
        expected[$leaf]=0
    done
    # Every key of expected is a name checked above, so it goes into SQL as it is.
    local query="" result got listed_parts=""
    if [[ -z $only_year ]]; then
        # A part the package does not have keeps rows of an older package; they would mix with the new ones.
        # Its name comes from the catalog, so the count is made in SQL with the name quoted.
        for key in "${!expected[@]}"; do
            if [[ $key == hotspot_* ]]; then
                listed_parts+="${listed_parts:+,}$key"
            fi
        done
        result=$(printf '%s\n' "SELECT c.relname, (xpath('/row/n/text()', query_to_xml(
                                     format('SELECT count(*) AS n FROM firms.%I', c.relname), false, true, '')))[1]
                                 FROM (SELECT relid FROM pg_partition_tree('firms.hotspot') WHERE isleaf
                                       UNION ALL
                                       SELECT relid FROM pg_partition_tree('firms.hotspot_static') WHERE isleaf) AS p
                                 JOIN pg_class c ON c.oid = p.relid
                                 WHERE c.relname <> ALL (string_to_array(:'listed', ','));" |
            "${PSQL[@]}" -A -t -F '|' -v listed="$listed_parts" -f -)
        while IFS='|' read -r leaf got; do
            if [[ -n $leaf && $got != 0 ]]; then
                unlisted[$leaf]=$got
            fi
        done <<<"$result"
    fi
    # The parts are counted by batch in the same pass: the journal takes its counts from them.
    for key in "${!expected[@]}"; do
        if [[ $key == *" "* ]]; then
            query+="${query:+ UNION ALL }SELECT '$key', NULL, count(*) FROM firms.${key%% *}
                    WHERE version = '${key#* }'"
        elif [[ $key == hotspot_* ]]; then
            query+="${query:+ UNION ALL }SELECT '$key', batch_id, count(*) FROM firms.$key GROUP BY batch_id"
        else
            query+="${query:+ UNION ALL }SELECT '$key', NULL, count(*) FROM firms.$key"
        fi
    done
    result=$("${PSQL[@]}" -A -t -F '|' -c "$query")
    declare -A counted=() by_batch=()
    local batch n
    while IFS='|' read -r key batch n; do
        if [[ -n $key ]]; then
            counted[$key]=$((${counted[$key]:-0} + n))
            if [[ $batch =~ ^[0-9]+$ ]]; then
                by_batch[$batch]=$((${by_batch[$batch]:-0} + n))
            fi
        fi
    done <<<"$result"
    local -a mismatches=()
    for key in "${!expected[@]}"; do
        got=${counted[$key]:-0}
        if [[ $got != "${expected[$key]}" ]]; then
            mismatches+=("$key: ${expected[$key]} rows in manifest.json, $got in the database")
        fi
    done
    LOADED_BATCHES=""
    for batch in "${!by_batch[@]}"; do
        LOADED_BATCHES+="${LOADED_BATCHES:+, }($batch, ${by_batch[$batch]})"
    done
    LOADED_BATCHES=${LOADED_BATCHES:+VALUES $LOADED_BATCHES}
    for leaf in "${!unlisted[@]}"; do
        mismatches+=("$leaf: not in manifest.json, ${unlisted[$leaf]} rows in the database")
    done
    if ((${#mismatches[@]})); then
        printf 'MISMATCH %s\n' "${mismatches[@]}" | sort
        local listed
        listed=$(printf '%s; ' "${mismatches[@]}")
        finish_runs failed "row counts differ from manifest.json: ${listed%; }"
        exit 1
    fi

    step "9. dataset"
    local keep_dataset="false"
    if [[ -n $only_year ]]; then
        keep_dataset="true"
    fi
    # A package of one year updates the database of the full package: that keeps its name, scope and countries,
    # takes the newer built_at and lists the update in manifest -> 'updates'.
    manifest_sql "BEGIN;
                  UPDATE firms.dataset d
                  SET built_at = greatest(d.built_at, (s.m ->> 'built_at')::timestamptz),
                      manifest = coalesce(d.manifest, '{}'::jsonb) || jsonb_build_object('updates',
                          coalesce(d.manifest -> 'updates', '[]'::jsonb) || jsonb_build_array(jsonb_build_object(
                              'name', s.m ->> 'name', 'built_at', s.m -> 'built_at', 'only_year', ${only_year:-0},
                              'restored_at', now())))
                  FROM (SELECT :'manifest'::jsonb AS m) AS s
                  WHERE $keep_dataset;
                  DELETE FROM firms.dataset WHERE NOT $keep_dataset;
                  INSERT INTO firms.dataset (name, scope, countries, built_at, manifest)
                  SELECT m ->> 'name',
                         coalesce(m ->> 'scope',
                                  CASE WHEN jsonb_typeof(m -> 'countries') = 'array' THEN 'countries' ELSE 'world' END),
                         CASE WHEN jsonb_typeof(m -> 'countries') = 'array'
                              THEN ARRAY(SELECT jsonb_array_elements_text(m -> 'countries')) END,
                         (m ->> 'built_at')::timestamptz, m
                  FROM (SELECT :'manifest'::jsonb AS m) AS s
                  WHERE NOT EXISTS (SELECT 1 FROM firms.dataset);
                  COMMIT;" >/dev/null

    step "10. journal"
    finish_runs success
    say "OK"
}

if [[ ${1-} == __load ]]; then
    cd "$PKG_DIR"
    load_job "$2"
    exit 0
fi
main "$@"
