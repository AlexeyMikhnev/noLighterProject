"""Проверка scripts/migrate_db.py на базе старой версии (light/dark, тексты без HTML)."""
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "migrate_db.py"

OLD = """
CREATE TABLE users (id INTEGER PRIMARY KEY, nickname TEXT);
CREATE TABLE stories (id INTEGER NOT NULL, contest_id INTEGER NOT NULL, author_id INTEGER NOT NULL,
  title VARCHAR(200) NOT NULL, body TEXT NOT NULL, anon_number INTEGER, created_at DATETIME, updated_at DATETIME,
  PRIMARY KEY (id), CONSTRAINT uq_story_author UNIQUE (contest_id, author_id),
  CONSTRAINT uq_story_anon UNIQUE (contest_id, anon_number));
CREATE TABLE ratings (id INTEGER NOT NULL, story_id INTEGER NOT NULL, rater_id INTEGER NOT NULL,
  impression INTEGER NOT NULL, theme INTEGER NOT NULL, style INTEGER NOT NULL,
  light INTEGER NOT NULL, dark INTEGER NOT NULL, adventure INTEGER NOT NULL,
  PRIMARY KEY (id), CONSTRAINT uq_rating UNIQUE (story_id, rater_id),
  CONSTRAINT ck_rating_light CHECK (light BETWEEN 1 AND 5), CONSTRAINT ck_rating_dark CHECK (dark BETWEEN 1 AND 5),
  FOREIGN KEY(story_id) REFERENCES stories (id), FOREIGN KEY(rater_id) REFERENCES users (id));
CREATE INDEX ix_ratings_story_id ON ratings (story_id);
INSERT INTO users VALUES (1,'a'),(2,'b');
INSERT INTO stories (id, contest_id, author_id, title, body, anon_number) VALUES
  (1,1,1,'T','Первый абзац\nвторая строка\n\n<script>alert(1)</script> & 2 < 3',1);
INSERT INTO ratings VALUES (1,1,2,4,3,5, 5,1, 2), (2,1,1,3,3,3, 1,5, 3);
"""


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)


@pytest.fixture
def old_db(tmp_path):
    p = tmp_path / "old.db"
    con = sqlite3.connect(p)
    con.executescript(OLD)
    con.commit()
    con.close()
    return p


def test_migrates_old_db(old_db):
    r = run(old_db, "--dry-run")
    assert r.returncode == 0 and "A (" in r.stdout and "B (" in r.stdout
    assert "light" in sqlite3.connect(old_db).execute("SELECT group_concat(name) FROM pragma_table_info('ratings')").fetchone()[0]

    r = run(old_db)
    assert r.returncode == 0, r.stdout + r.stderr
    con = sqlite3.connect(old_db)
    body = con.execute("SELECT body FROM stories").fetchone()[0]
    assert "<script" not in body and "&lt;script&gt;" in body
    assert body.startswith("<p>Первый абзац<br>вторая строка</p>")
    assert [tuple(x) for x in con.execute("SELECT id, mood FROM ratings ORDER BY id")] == [(1, 5), (2, 1)]
    assert list(old_db.parent.glob("old.db.bak-*"))
    cols = [x[1] for x in con.execute("PRAGMA table_info(ratings)")]
    assert "light" not in cols and "mood" in cols
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("INSERT INTO ratings VALUES (9,1,2,1,1,1,9,1)")

    r = run(old_db)  # повторный запуск
    assert "уже актуальна" in r.stdout


def test_not_contest_db(tmp_path):
    p = tmp_path / "x.db"
    sqlite3.connect(p).execute("CREATE TABLE t (a)").connection.commit()
    assert run(p).returncode != 0
