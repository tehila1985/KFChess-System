-- Chess backend database schema
-- All table/column names are referenced only through repository methods,
-- never via raw strings in service code.

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    elo           INTEGER NOT NULL DEFAULT 1200,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    last_login_at TEXT
);

CREATE TABLE IF NOT EXISTS games (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    white_user_id    INTEGER NOT NULL REFERENCES users(id),
    black_user_id    INTEGER NOT NULL REFERENCES users(id),
    result           TEXT NOT NULL,
    end_reason       TEXT NOT NULL,
    white_elo_before INTEGER NOT NULL,
    black_elo_before INTEGER NOT NULL,
    white_elo_after  INTEGER NOT NULL,
    black_elo_after  INTEGER NOT NULL,
    room_id          TEXT,
    started_at       TEXT NOT NULL,
    ended_at         TEXT
);

CREATE TABLE IF NOT EXISTS moves (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id    INTEGER NOT NULL REFERENCES games(id),
    ply_number INTEGER NOT NULL,
    move_san   TEXT NOT NULL,
    played_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_users_elo ON users(elo);
CREATE INDEX IF NOT EXISTS idx_games_users ON games(white_user_id, black_user_id);
