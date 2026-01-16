from fastapi import APIRouter

from .v1 import epc, health, meta, ppd, rightmove

api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router)
api_router.include_router(ppd.router)
api_router.include_router(epc.router)
api_router.include_router(rightmove.router)
api_router.include_router(meta.router)
