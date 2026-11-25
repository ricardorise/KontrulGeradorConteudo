from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from studio.interfaces.http.container import UseCases
from studio.interfaces.http.deps import require_api_key
from studio.interfaces.http.routers import conversations, guidelines, news, publications, renders, scripts
from studio.shared.domain.errors import Conflict, DomainError, NotFound


def build_app(use_cases: UseCases, *, api_key: str | None, cors_origins: tuple[str, ...], lifespan=None) -> FastAPI:
    app = FastAPI(title="Kontrul Content Studio", version="0.1.0", lifespan=lifespan)
    app.state.use_cases = use_cases
    app.state.api_key = api_key
    if cors_origins:
        app.add_middleware(
            CORSMiddleware, allow_origins=list(cors_origins), allow_methods=["*"], allow_headers=["*"]
        )

    api = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])
    for module in (news, scripts, conversations, guidelines, renders, publications):
        api.include_router(module.router)
    app.include_router(api)

    @app.get("/health", include_in_schema=False)
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.exception_handler(DomainError)
    async def domain_error(_: Request, exc: DomainError) -> JSONResponse:
        status = 404 if isinstance(exc, NotFound) else 409 if isinstance(exc, Conflict) else 422
        return JSONResponse(status_code=status, content={"detail": str(exc)})

    return app
