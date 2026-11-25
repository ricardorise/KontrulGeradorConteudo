import hmac

from fastapi import Header, HTTPException, Request

from studio.interfaces.http.container import UseCases


def use_cases(request: Request) -> UseCases:
    return request.app.state.use_cases


async def require_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    expected: str | None = request.app.state.api_key
    if expected and not (x_api_key and hmac.compare_digest(x_api_key, expected)):
        raise HTTPException(status_code=401, detail="API key inválida.")
