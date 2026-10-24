from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .db import init_db
from .routers import admin, auth, contest, me, results, rules, stories, voting


@asynccontextmanager
async def lifespan(_: FastAPI):
    if config.SECRET_KEY == config.DEV_SECRET:
        print("WARNING: используется SECRET_KEY по умолчанию, задайте свой в окружении")
    init_db()
    yield


app = FastAPI(title="Негрелочка", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (auth, contest, stories, voting, results, me, admin, rules):
    app.include_router(r.router)

# Если фронтенд собран (npm run build), отдаём его же из FastAPI.
DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if (DIST / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path.startswith("api/"):
            raise HTTPException(404)
        target = (DIST / full_path).resolve()
        if full_path and target.is_file() and target.is_relative_to(DIST.resolve()):
            return FileResponse(target)
        return FileResponse(DIST / "index.html")
