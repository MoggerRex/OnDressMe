from fastapi import APIRouter, File, HTTPException, UploadFile
from app.services.colorimetry.analyzer import analyze_face_colorimetry

router = APIRouter(prefix="/api")


@router.post("/colorimetry")
async def analyze_colorimetry(
    profile_id: str, image: UploadFile = File(...)
) -> dict:
    try:
        analysis_result = await analyze_face_colorimetry(image)
        return {
            "profile_id": profile_id,
            "status": "completed",
            "result": analysis_result,
        }
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error procesando la imagen para colorimetría: {str(e)}",
        )


@router.get("/profile/{profile_id}")
def get_profile(profile_id: str) -> None:
    del profile_id
    raise HTTPException(
        status_code=501,
        detail="Profile persistence is reserved for a later implementation phase",
    )


@router.get("/wardrobe")
def get_wardrobe(profile_id: str) -> None:
    del profile_id
    raise HTTPException(
        status_code=501,
        detail="Wardrobe persistence is reserved for a later implementation phase",
    )