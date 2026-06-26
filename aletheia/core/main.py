from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from aletheia.core.api.routes import router
from aletheia.core.config.settings import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ALETHEIA",
        version="0.1.0",
        description="India-first multi-agent financial intelligence platform",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)

    @app.get("/")
    async def root() -> dict[str, str]:
        return {
            "service": "ALETHEIA",
            "version": "0.1.0",
            "docs": "/docs",
        }

    return app


app = create_app()


