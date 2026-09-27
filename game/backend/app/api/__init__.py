from fastapi import APIRouter

from app.api import routes_session, routes_world


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(routes_session.router)
    router.include_router(routes_world.router)
    return router
