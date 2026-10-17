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
MAX_BODY_CHARS = 60_000
MAX_REVIEW_CHARS = 5_000
STARS_PER_USER = 3

# Шкалы оценки (1..5). Ключ -> (название, подсказка).
# Меняются только здесь (+ колонки в models.Rating): фронтенд получает их из API.
SCALES = [
    ("impression", "Общее впечатление", "Насколько рассказ понравился в целом"),
    ("theme", "Верность теме", "Насколько точно рассказ раскрывает тему конкурса"),
    ("style", "Красота слога", "Язык, ритм, образность"),
    ("light", "«Светлость»", "Тепло, надежда, радость: насколько рассказ светлый"),
    ("dark", "«Тёмность»", "Тревога, мрак, горечь: насколько рассказ тёмный"),
    ("adventure", "Авантюризм", "Динамика, риск, дух приключения"),
]
SCALE_KEYS = [k for k, _, _ in SCALES]
