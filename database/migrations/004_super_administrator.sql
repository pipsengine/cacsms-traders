PRAGMA foreign_keys=ON;
ALTER TABLE users ADD COLUMN is_system_protected INTEGER NOT NULL DEFAULT 0;
