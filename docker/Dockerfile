FROM docker.io/library/postgres:17

RUN apt-get update && \
    apt-get install -y --no-install-recommends postgresql-17-pgvector && \
    rm -rf /var/lib/apt/lists/*

COPY 01-init.sql /docker-entrypoint-initdb.d/01-init.sql
COPY 02-data.sql /docker-entrypoint-initdb.d/02-data.sql

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB} || exit 1