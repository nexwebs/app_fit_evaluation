## Archivos

- `01_schema_completo.sql` - Schema completo (58 tablas)
- `02_datos_configuracion.sql` - Plan de cuentas, roles, monedas
- `00_crear_base_datos.sql` - Guia

## Como usar

```bash
# 1. Eliminar y recrear la BD
psql -U postgres -c "DROP DATABASE IF EXISTS fitdb_evaluation_v2;"
psql -U postgres -c "CREATE DATABASE fitdb_evaluation_v2;"

# 2. Ejecutar en orden
#psql -U postgres -d fitdb_evaluation_v2 -f docker/01-init.sql
psql -U postgres -d fitdb_evaluation_v2 -f docker/02-data.sql
uv run uvicorn app.main:app --reload --port 8000
#pg_dump -U postgres -d fitdb_evaluation_v2 -f docker/backup.sql


psql -U postgres -d fitdb_evaluation_v2 -f docker/backup.sql

uv run gunicorn app.main:app -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

