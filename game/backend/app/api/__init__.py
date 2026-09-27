from fastapi import APIRouter

from app.api import routes_clans, routes_economy, routes_session, routes_world


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(routes_session.router)
    router.include_router(routes_world.router)
    router.include_router(routes_economy.router)
    router.include_router(routes_clans.router)
    return router
