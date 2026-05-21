from fastapi import APIRouter

router = APIRouter()


@router.get("")
def usage_summary() -> dict[str, object]:
    return {
        "projects": 0,
        "users": 0,
        "steps_generated": 0,
        "downloads": 0,
    }
