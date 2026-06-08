CREATE TABLE IF NOT EXISTS public.users (
  id INTEGER PRIMARY KEY,
  email TEXT NOT NULL
);

CREATE VIEW active_users AS
SELECT * FROM public.users;

CREATE UNIQUE INDEX idx_users_email ON public.users(email);
