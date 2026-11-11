#!/usr/bin/env python3
"""Миграция базы конкурса со старых версий до текущей (с «угадайкой»).

Использование (из папки contest/backend, бэкенд при этом ОСТАНОВИТЕ):

    python scripts/migrate_db.py                  # база из DATABASE_URL или ./contest.db
    python scripts/migrate_db.py путь\\к\\contest.db
    python scripts/migrate_db.py --dry-run        # только показать, что будет сделано
    python scripts/migrate_db.py --no-backup      # без резервной копии (не советую)

Что делает (только если нужно, повторный запуск безопасен):
  A. stories: добавляет столбец disclaimer и переводит тексты рассказов из простого текста
     в очищенный HTML (новая версия показывает тексты как HTML, поэтому старый текст с «<»
     обязательно экранируется).
  B. ratings: столбцы light/dark заменяются одной шкалой mood = (light + 7 - dark) // 2,
     таблица пересобирается вместе с CHECK-ограничениями (SQLite не умеет их менять на месте).

Новые таблицы (settings, surveys, reviews, guesses, stars) скрипт не трогает:
их при старте создаёт само приложение (create_all), данные в них начинаются с нуля.
Для баз версий 3–5 миграция не нужна: достаточно запустить приложение.
Только стандартная библиотека + app.richtext из проекта.
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime
from html import escape
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.richtext import clean  # noqa: E402

RATINGS_NEW = """
CREATE TABLE ratings_new (
    id INTEGER NOT NULL,
    story_id INTEGER NOT NULL,
    rater_id INTEGER NOT NULL,
    impression INTEGER NOT NULL,
    theme INTEGER NOT NULL,
    style INTEGER NOT NULL,
    mood INTEGER NOT NULL,
    adventure INTEGER NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_rating UNIQUE (story_id, rater_id),
    CONSTRAINT ck_rating_impression CHECK (impression BETWEEN 1 AND 5),
    CONSTRAINT ck_rating_theme CHECK (theme BETWEEN 1 AND 5),
    CONSTRAINT ck_rating_style CHECK (style BETWEEN 1 AND 5),
    CONSTRAINT ck_rating_mood CHECK (mood BETWEEN 1 AND 5),
    CONSTRAINT ck_rating_adventure CHECK (adventure BETWEEN 1 AND 5),
    FOREIGN KEY(story_id) REFERENCES stories (id),
    FOREIGN KEY(rater_id) REFERENCES users (id)
)
"""


def plain_to_html(v: str) -> str:
    """Та же логика, что в app.schemas: пустая строка делит абзацы, одиночный перенос — <br>."""
    v = v.replace("\r\n", "\n").strip()
    return "".join(
        f"<p>{escape(p.strip(), quote=False).replace(chr(10), '<br>')}</p>" for p in v.split("\n\n") if p.strip()
    )


def default_path() -> str:
    url = os.getenv("DATABASE_URL", "sqlite:///./contest.db")
    if not url.startswith("sqlite:///"):
        sys.exit(f"Скрипт работает только с SQLite, а в DATABASE_URL: {url}")
    return url[len("sqlite:///"):]


def columns(con, table):
    return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]


def tables(con):
    return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


def plan(con):
    """Что нужно сделать: список шагов 'A'/'B' и список предупреждений."""
    have = tables(con)
    steps, notes = [], []
    if "stories" not in have or "ratings" not in have or "users" not in have:
        sys.exit("Это не база конкурса: нет таблиц users/stories/ratings.")
    if "disclaimer" not in columns(con, "stories"):
        steps.append("A")
    rc = columns(con, "ratings")
    if "light" in rc or "dark" in rc:
        if not {"light", "dark"} <= set(rc):
            sys.exit(f"Нестандартная таблица ratings (столбцы {rc}): миграция остановлена, ничего не изменено.")
        steps.append("B")
    elif "mood" not in rc:
        sys.exit(f"Нестандартная таблица ratings (столбцы {rc}): миграция остановлена, ничего не изменено.")
    missing = {"settings", "surveys", "reviews", "guesses", "stars"} - have
    if missing:
        notes.append("Эти таблицы создаст приложение при первом запуске: " + ", ".join(sorted(missing)))
    return steps, notes


def step_a(con):
    con.execute("ALTER TABLE stories ADD COLUMN disclaimer TEXT NOT NULL DEFAULT ''")
    warns, n = [], 0
    for sid, anon, body in con.execute("SELECT id, anon_number, body FROM stories").fetchall():
        html = clean(plain_to_html(body or ""))
        if not html:
            warns.append(f"рассказ №{anon} (id {sid}): после очистки текст пуст, оставлен как был")
            continue
        con.execute("UPDATE stories SET body=? WHERE id=?", (html, sid))
        n += 1
    return n, warns


def step_b(con):
    n_bad = con.execute(
        "SELECT COUNT(*) FROM ratings WHERE light NOT BETWEEN 1 AND 5 OR dark NOT BETWEEN 1 AND 5"
    ).fetchone()[0]
    con.execute(RATINGS_NEW)
    con.execute(
        "INSERT INTO ratings_new (id, story_id, rater_id, impression, theme, style, mood, adventure) "
        "SELECT id, story_id, rater_id, impression, theme, style, "
        "MAX(1, MIN(5, (light + 7 - dark) / 2)), adventure FROM ratings"
    )
    con.execute("DROP TABLE ratings")
    con.execute("ALTER TABLE ratings_new RENAME TO ratings")
    con.execute("CREATE INDEX ix_ratings_story_id ON ratings (story_id)")
    return con.execute("SELECT COUNT(*) FROM ratings").fetchone()[0], n_bad


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("db", nargs="?", help="путь к файлу SQLite")
    ap.add_argument("--dry-run", action="store_true", help="ничего не менять, только показать план")
    ap.add_argument("--no-backup", action="store_true", help="не делать резервную копию")
    args = ap.parse_args()

    path = Path(args.db or default_path())
    if not path.is_file():
        sys.exit(f"Файл базы не найден: {path.resolve()}")

    con = sqlite3.connect(path, isolation_level=None)  # транзакциями управляем сами
    con.execute("PRAGMA busy_timeout=2000")
    steps, notes = plan(con)
    print(f"База: {path.resolve()}")
    for n in notes:
        print("ℹ", n)
    if not steps:
        print("База уже актуальна, миграция не требуется.")
        return
    names = {"A": "тексты рассказов → HTML, столбец disclaimer", "B": "оценки: light/dark → mood"}
    print("Нужно:", "; ".join(f"{s} ({names[s]})" for s in steps))
    if args.dry_run:
        print("--dry-run: ничего не изменено.")
        return

    try:
        con.execute("BEGIN IMMEDIATE")  # заодно проверяет, что бэкенд не держит базу
        con.execute("ROLLBACK")
    except sqlite3.OperationalError as e:
        sys.exit(f"База занята ({e}). Остановите бэкенд и повторите.")

    if not args.no_backup:
        bak = path.with_name(f"{path.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
        dst = sqlite3.connect(bak)
        with dst:
            con.backup(dst)
        dst.close()
        print(f"Резервная копия: {bak}")

    con.execute("PRAGMA foreign_keys=OFF")  # вне транзакции, иначе не сработает
    try:
        con.execute("BEGIN IMMEDIATE")
        if "A" in steps:
            n, warns = step_a(con)
            print(f"A: обновлено текстов рассказов: {n}")
            for w in warns:
                print("⚠", w)
        if "B" in steps:
            n, bad = step_b(con)
            print(f"B: перенесено оценок: {n}")
            if bad:
                print(f"⚠ значения вне 1..5 у {bad} оценок: результат ограничен диапазоном")
        fk = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk:
            raise RuntimeError(f"нарушены внешние ключи: {fk[:5]}")
        con.execute("COMMIT")
    except BaseException as e:
        if con.in_transaction:
            con.execute("ROLLBACK")
        sys.exit(f"Ошибка, база не изменена: {e}")
    ok = con.execute("PRAGMA integrity_check").fetchone()[0]
    print("Проверка целостности:", ok)
    print("Готово. Запускайте приложение: недостающие таблицы оно создаст само.")


if __name__ == "__main__":
    main()
