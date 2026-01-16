from fastapi import APIRouter

from .v1 import epc, health, ppd

api_router = APIRouter(prefix="/v1")
api_router.include_router(health.router)
api_router.include_router(ppd.router)
api_router.include_router(epc.router)
