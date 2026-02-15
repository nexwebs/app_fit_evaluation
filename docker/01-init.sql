CREATE EXTENSION IF NOT EXISTS vector;

ALTER USER postgres WITH PASSWORD 'adminp';

-- Para evitar locks largos
SET lock_timeout = '5s';
SET statement_timeout = '30s';
-- fitdb_evaluation

 