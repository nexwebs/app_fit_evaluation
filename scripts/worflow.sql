
-- 1. Limpiar evaluaciones huérfanas (sin respuestas) existentes
UPDATE evaluations
SET 
    status = 'abandoned',
    completed_at = CURRENT_TIMESTAMP
WHERE status = 'in_progress'
  AND NOT EXISTS (
      SELECT 1 FROM evaluation_answers WHERE evaluation_id = evaluations.id
  );

-- 2. Verificar el estado después de la limpieza
SELECT 
    status,
    COUNT(*) as count,
    MIN(started_at) as oldest,
    MAX(started_at) as newest
FROM evaluations
GROUP BY status
ORDER BY status;

-- 3. Probar la función con un usuario específico
SELECT * FROM can_reapply_to_position(
    (SELECT id FROM prospects WHERE email = 'clblommberg@gmail.com'),
    (SELECT id FROM job_positions WHERE title = 'Asistente Administrativo'),
    30
);

-- ============================================================
-- QUERIES DE DIAGNÓSTICO
-- ============================================================

-- Ver todas las evaluaciones de un usuario específico
SELECT 
    e.id,
    e.status,
    e.started_at,
    e.completed_at,
    e.current_test,
    e.current_question,
    (SELECT COUNT(*) FROM evaluation_answers WHERE evaluation_id = e.id) as answer_count,
    jp.title as position
FROM evaluations e
JOIN job_positions jp ON e.position_id = jp.id
WHERE e.prospect_id = (SELECT id FROM prospects WHERE email = 'clblommberg@gmail.com')
ORDER BY e.started_at DESC;

-- Ver evaluaciones abandonadas sin respuestas (las que NO deberían bloquear)
SELECT 
    e.id,
    e.status,
    e.started_at,
    p.email,
    jp.title,
    (SELECT COUNT(*) FROM evaluation_answers WHERE evaluation_id = e.id) as answer_count
FROM evaluations e
JOIN prospects p ON e.prospect_id = p.id
JOIN job_positions jp ON e.position_id = jp.id
WHERE e.status = 'abandoned'
  AND NOT EXISTS (SELECT 1 FROM evaluation_answers WHERE evaluation_id = e.id)
ORDER BY e.started_at DESC;
