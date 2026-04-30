-- Migration 009: Always-on work windows for justicia_xxi_web
-- schedule='{}' means no time restriction (active 24/7).
-- Applied 2026-04-30.

INSERT INTO work_windows (id, especialist_id, application_code, load_percentage, schedule, active)
SELECT
    gen_random_uuid(),
    e.id,
    'justicia_xxi_web',
    NULL,
    '{}',
    true
FROM especialist e
WHERE e.active = true
  AND NOT EXISTS (
    SELECT 1 FROM work_windows w
    WHERE w.especialist_id = e.id
      AND w.application_code = 'justicia_xxi_web'
  );



-- SPECIALIST ASSIGNMENT: justicia_xxi_web
-- SPECIALIST
  SELECT
      a.id            AS assignment_id,
      a.assigned_at,
      a.level,
      e.code          AS specialist_code,
      e.name          AS specialist_name,
      c.conversation_id,
      c.subject,
      c.sender_email,
      c.folder
  FROM assignments a
  JOIN especialist e ON e.id = a.especialist_id
  JOIN conversations c ON c.id = a.thread_id
  WHERE a.application_code = 'justicia_xxi_web'
  ORDER BY a.assigned_at DESC
  LIMIT 20;
