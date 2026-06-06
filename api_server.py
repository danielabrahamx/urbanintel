"""
FastAPI server for video analysis endpoints.
Used by the frontend for TfL clips and manual uploads.
"""

import os

import requests
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, field_validator
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from shared.tfl_client import TflClient
from shared.video_analyzer import OpenRouterAnalyzer, download_video  # noqa: F401  (download_video kept for watcher)
from shared.config_loader import load_config
from shared.incident_repository import IncidentRepository

app = FastAPI(title="Urban Intelligence API")

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

#: OpenRouter model reported in the health check.
_MODEL = "minimax/minimax-m3"


class AnalyzeRequest(BaseModel):
    video_url: str
    camera_id: Optional[str] = None
    camera_name: Optional[str] = None
    lat: Optional[float] = None
    lon: Optional[float] = None
    source: str = "tfl"
    created_by: Optional[str] = None
    second_opinion: bool = False

    @field_validator("video_url")
    @classmethod
    def validate_video_url(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("video_url must start with http:// or https://")
        return v

    @field_validator("lat")
    @classmethod
    def validate_lat(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-90 <= v <= 90):
            raise ValueError("lat must be between -90 and 90")
        return v

    @field_validator("lon")
    @classmethod
    def validate_lon(cls, v: Optional[float]) -> Optional[float]:
        if v is not None and not (-180 <= v <= 180):
            raise ValueError("lon must be between -180 and 180")
        return v

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str) -> str:
        if v not in ("tfl", "manual", "upload"):
            raise ValueError("source must be one of: tfl, manual, upload")
        return v


class AnalyzeResponse(BaseModel):
    incident_detected: bool
    severity: str
    incidents: list
    scene_summary: str
    reasoning: str
    saved_incident: Optional[dict] = None


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_video_endpoint(request: AnalyzeRequest):
    """Analyze a video from URL, persist to DB, and return result."""
    cfg = load_config()

    # Use different model for second opinion
    if request.second_opinion:
        from shared.video_analyzer import GeminiAnalyzer
        gemini_key = os.getenv("GEMINI_API_KEY")
        if not gemini_key:
            raise HTTPException(status_code=500, detail="GEMINI_API_KEY not configured for second opinion")
        analyzer = GeminiAnalyzer(api_key=gemini_key)
    else:
        try:
            api_key = cfg.require_openrouter_key()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
        analyzer = OpenRouterAnalyzer(api_key=api_key, model=_MODEL)

    repo = IncidentRepository.from_env()

    try:
        # OpenRouterAnalyzer passes the URL directly to the model.
        # minimax/minimax-m3 silently returns null for base64 data URLs — it
        # requires a real HTTP/HTTPS URL. GeminiAnalyzer still uses the Files
        # API and needs a local download.
        if request.second_opinion:
            video_path = None
            try:
                video_path = download_video(request.video_url)
                result = analyzer.analyze(video_path)
            finally:
                if video_path and os.path.exists(video_path):
                    os.unlink(video_path)
        else:
            result = analyzer.analyze_url(request.video_url)

        # Persist to DB via IncidentRepository
        saved_incident = None
        if repo:
            camera_id = request.camera_id or "manual"
            camera_name = request.camera_name or camera_id
            try:
                repo.save(
                    result,
                    camera_id=camera_id,
                    camera_name=camera_name,
                    lat=request.lat,
                    lon=request.lon,
                    source=request.source,
                )
                saved_incident = {
                    "camera_id": camera_id,
                    "camera_name": camera_name,
                    "severity": result.get("severity"),
                    "incident_detected": result.get("incident_detected"),
                }
            except Exception as db_exc:
                # Don't fail the analysis if DB write fails - log and continue
                print(f"[warn] DB write failed: {db_exc}")

        return AnalyzeResponse(
            incident_detected=result.get("incident_detected", False),
            severity=result.get("severity", "none"),
            incidents=result.get("incidents", []),
            scene_summary=result.get("scene_summary", ""),
            reasoning=result.get("reasoning", ""),
            saved_incident=saved_incident,
        )

    except (ValueError, requests.HTTPError, requests.Timeout, requests.RequestException) as e:
        raise HTTPException(status_code=400, detail=f"Failed to process video: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")


@app.post("/upload")
async def upload_and_analyze_endpoint(request: AnalyzeRequest):
    """Analyze a manually-uploaded video URL (already in Supabase Storage)."""
    # Reuse same logic as /analyze but with source forced to "manual"
    # Pydantic v2 models are immutable - use model_copy to update
    request = request.model_copy(update={"source": "manual"})
    return await analyze_video_endpoint(request)


@app.get("/cameras/{camera_id}/video-url")
async def get_camera_video_url_endpoint(camera_id: str):
    """Fetch the current video URL for a TfL JamCam."""
    cfg = load_config()
    tfl = TflClient(app_key=cfg.tfl_app_key)

    try:
        video_url, camera_name, lat, lon = tfl.get_camera_video_url(camera_id)
        return {
            "camera_id": camera_id,
            "camera_name": camera_name,
            "video_url": video_url,
            "lat": lat,
            "lon": lon,
        }
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TfL API error: {str(exc)}")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    repo = IncidentRepository.from_env()
    return {
        "status": "ok",
        "model": _MODEL,
        "db": "connected" if (repo and repo.is_connected) else "not configured",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
