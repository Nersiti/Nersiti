from fastapi import APIRouter

from app.api import (
    routes_clans,
    routes_economy,
    routes_leaderboard,
    routes_map,
    routes_session,
    routes_shop,
    routes_tasks,
    routes_world,
)


def build_api_router() -> APIRouter:
    router = APIRouter()
    router.include_router(routes_session.router)
    router.include_router(routes_world.router)
    router.include_router(routes_economy.router)
    router.include_router(routes_clans.router)
    router.include_router(routes_map.router)
    router.include_router(routes_leaderboard.router)
    router.include_router(routes_shop.router)
    router.include_router(routes_tasks.router)
    return router
