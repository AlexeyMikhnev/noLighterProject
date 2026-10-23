import os

DEV_SECRET = "dev-secret-change-me-dev-secret-change-me"

SECRET_KEY = os.getenv("SECRET_KEY", DEV_SECRET)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./contest.db")
TOKEN_TTL_MINUTES = int(os.getenv("TOKEN_TTL_MINUTES", str(60 * 24 * 7)))

# Организатор создаётся при первом запуске, если в базе ещё нет ни одного.
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "admin@example.com")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin12345")
ADMIN_NICKNAME = os.getenv("ADMIN_NICKNAME", "Организатор")

CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")

MAX_TITLE_CHARS = 200
MAX_BODY_CHARS = 10_000  # знаков видимого текста (без разметки)
MAX_BODY_HTML_CHARS = 60_000  # грубый потолок на сырой HTML от редактора, до очистки
MAX_DISCLAIMER_CHARS = 1_000
MAX_REVIEW_CHARS = 5_000
STARS_PER_USER = 3

# Шкалы оценки (1..5). Ключ -> (название, подсказка).
# Меняются только здесь (+ колонки в models.Rating): фронтенд получает их из API.
SCALES = [
    ("impression", "Общее впечатление", "Насколько рассказ понравился в целом"),
    ("theme", "Верность теме", "Насколько точно рассказ раскрывает тему конкурса"),
    ("style", "Красота слога", "Язык, ритм, образность"),
    ("mood", "«Светлость»", "1 — тёмный: тревога, мрак, горечь; 5 — светлый: тепло, надежда, радость"),
    ("adventure", "Авантюризм", "Динамика, риск, дух приключения"),
]
SCALE_KEYS = [k for k, _, _ in SCALES]

# Опросник для статистики (на оценки и топы не влияет). Заполняется в фазе оценивания, по одному на пару
# (рассказ, читатель). Все ответы необязательны. Фронтенд получает вопросы из API.
# type: "multi" — несколько вариантов, "single" — один, "bool" — да/нет. Ключи вариантов хранятся в базе.
SURVEY = [
    {
        "key": "genres",
        "label": "Жанр",
        "type": "multi",
        "options": [
            ("drama", "Драма"),
            ("comedy", "Комедия"),
            ("detective", "Детектив"),
            ("thriller", "Триллер"),
            ("adventure", "Приключение"),
        ],
    },
    {
        "key": "settings",
        "label": "Сеттинг",
        "type": "multi",
        "options": [
            ("postapoc", "Постапокалипсис"),
            ("realism", "Реализм"),
            ("hist_realism", "Ист. реализм"),
            ("fantasy", "Фентези"),
            ("scifi", "Sci-fi"),
            ("magic_realism", "Магический реализм"),
        ],
    },
    {
        "key": "hero_gender",
        "label": "Пол главного героя",
        "type": "single",
        "options": [("male", "Мужчина"), ("female", "Женщина")],
    },
    {"key": "about_children", "label": "Рассказ про детей?", "type": "bool"},
    {"key": "about_animals", "label": "Рассказ про животных?", "type": "bool"},
    {"key": "someone_died", "label": "Умер ли кто-то в рассказе?", "type": "bool"},
    {"key": "has_guns", "label": "Есть ли в рассказе пушки?", "type": "bool"},
]
SURVEY_BY_KEY = {q["key"]: q for q in SURVEY}
SURVEY_BOOL_KEYS = [q["key"] for q in SURVEY if q["type"] == "bool"]
