from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from services.map_matching_service import MapMatchingService

app = FastAPI()
service = MapMatchingService()

class GPSRequest(BaseModel):
    bus_id: str
    route_id: str
    lat: float
    lon: float
    heading: Optional[float] = None
    timestamp: str


@app.get("/")
def root():
    return {
        "message": "Shuttle Map Matching Server is running"
    }


@app.get("/health")
def health_check():
    return service.health()

@app.post("/mapmatch")
def mapmatch(gps: GPSRequest):
    return service.process_gps(
        bus_id=gps.bus_id,
        route_id=gps.route_id,
        lat=gps.lat,
        lon=gps.lon,
        heading=gps.heading,
        timestamp=gps.timestamp,
    )