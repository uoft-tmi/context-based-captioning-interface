CREATE UNIQUE INDEX one_active_session_per_user 
ON sessions (user_id) 
WHERE status = 'active';