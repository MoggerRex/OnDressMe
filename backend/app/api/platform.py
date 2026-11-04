from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/api")


def _not_ready(capability: str) -> None:
    raise HTTPException(
        status_code=501,
        detail=f"{capability} is reserved for a later implementation phase",
    )


@router.post("/colorimetry")
def analyze_colorimetry(profile_id: str, image: UploadFile = File(...)) -> None:
    del profile_id, image
    _not_ready("Colorimetry processing")


@router.get("/profile/{profile_id}")
def get_profile(profile_id: str) -> None:
    del profile_id
    _not_ready("Profile persistence")


@router.get("/wardrobe")
def get_wardrobe(profile_id: str) -> None:
    del profile_id
    _not_ready("Wardrobe persistence")
