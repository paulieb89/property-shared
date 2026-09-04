from fastapi import APIRouter, Depends

from .strict_query import reject_unknown_query_params

from .v1 import analysis, companies_house, epc, health, meta, ppd, report, rightmove, stamp_duty
# from .v1 import planning  # Disabled: scraping requires UK residential IP

#: Applied at the router so every v1 route inherits it -- a per-route
#: opt-in would mean the next endpoint added silently goes back to
#: discarding typos, which is the failure this exists to stop.
api_router = APIRouter(
    prefix="/v1",
    dependencies=[Depends(reject_unknown_query_params)],
)
api_router.include_router(health.router)
api_router.include_router(ppd.router)
api_router.include_router(epc.router)
api_router.include_router(rightmove.router)
# api_router.include_router(planning.router)  # Disabled: scraping requires UK residential IP
api_router.include_router(report.router)
api_router.include_router(meta.router)
api_router.include_router(stamp_duty.router)
api_router.include_router(companies_house.router)
api_router.include_router(analysis.router)
