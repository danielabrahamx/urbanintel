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
from shared.video_analyzer import OpenRouterAnalyzer, download_video
from shared.config_loader import load_config

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


@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze_video_endpoint(request: AnalyzeRequest):
    """Analyze a video from URL (TfL or manual upload)."""
    cfg = load_config()

    try:
        api_key = cfg.require_openrouter_key()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    analyzer = OpenRouterAnalyzer(api_key=api_key, model=_MODEL)

    video_path = None
    try:
        video_path = download_video(request.video_url)

        result = analyzer.analyze(video_path)

        return AnalyzeResponse(
            incident_detected=result.get("incident_detected", False),
            severity=result.get("severity", "none"),
            incidents=result.get("incidents", []),
            scene_summary=result.get("scene_summary", ""),
            reasoning=result.get("reasoning", ""),
        )

    except (ValueError, requests.HTTPError, requests.Timeout, requests.RequestException) as e:
        raise HTTPException(status_code=400, detail=f"Failed to download video: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {str(e)}")
    finally:
        if video_path and os.path.exists(video_path):
            os.unlink(video_path)


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
    return {"status": "ok", "model": _MODEL}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
