from fastapi import APIRouter

router = APIRouter()


@router.get("/health", summary="Health check")
async def health() -> dict[str, str]:
    return {"status": "ok"}
