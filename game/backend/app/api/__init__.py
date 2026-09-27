from fastapi import APIRouter

from app.api import routes_session


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(routes_session.router)
    return router
