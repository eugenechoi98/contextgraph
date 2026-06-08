CREATE TABLE "user_accounts" (
  id INTEGER PRIMARY KEY,
  username TEXT NOT NULL
);

CREATE INDEX [idx_user_accounts_username] ON "user_accounts"(username);
