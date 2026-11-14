# Official postgres image + PostGIS from apt (works on Apple Silicon arm64)
FROM postgres:17

RUN apt-get update && apt-get install -y --no-install-recommends \
        postgresql-17-postgis-3 postgresql-17-postgis-3-scripts \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

COPY init-postgis.sql /docker-entrypoint-initdb.d/10-postgis.sql
