from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from pathlib import Path

from src.road_network import RoadNetwork
from services.map_matching_service import MapMatchingService

from services.firebase_service import (
    write_test_data,
    update_bus_location,
    start_bus_trip,
    end_bus_trip,
)

app = FastAPI()


# bus_id별 MapMatchingService 관리
services: dict[str, MapMatchingService] = {}


# route_id별 RoadNetwork 관리
road_networks: dict[str, RoadNetwork] = {}
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

ROUTE_NETWORK_FILES = {
    "route_001": {
        "nodes": DATA_DIR / "아산역" / "road_nodes.csv",
        "edges": DATA_DIR / "아산역" / "road_edges_bidirectional.csv",
    },
    "route_002": {
        "nodes": DATA_DIR / "천안터미널역" / "road_nodes.csv",
        "edges": DATA_DIR / "천안터미널역" / "road_edges_bidirectional.csv",
    },
}

def get_road_network(route_id: str) -> RoadNetwork:
    """
    route_id에 해당하는 RoadNetwork를 반환한다.
    최초 요청 시 한 번만 로딩한다.
    """

    if route_id not in ROUTE_NETWORK_FILES:
        raise ValueError(f"지원하지 않는 route_id입니다: {route_id}")

    if route_id not in road_networks:
        network_files = ROUTE_NETWORK_FILES[route_id]

        print(
            f"[ROAD NETWORK CREATED] "
            f"route_id={route_id}, "
            f"nodes={network_files['nodes']}, "
            f"edges={network_files['edges']}"
        )

        road_networks[route_id] = RoadNetwork(
            network_files["nodes"],
            network_files["edges"],
        )

    return road_networks[route_id]

class GPSRequest(BaseModel):
    bus_id: str
    route_id: str
    lat: float
    lon: float
    heading: Optional[float] = None
    timestamp: str

class TripRequest(BaseModel):
    bus_id: str
    route_id: str


"""
    bus_id에 해당하는 MapMatchingService 반환.

    처음 들어온 bus_id라면 새로운 서비스 인스턴스를 생성한다.
"""
def get_service(
    bus_id: str,
    route_id: str
) -> MapMatchingService:

    if bus_id not in services:
        print(
            f"[SERVICE CREATED] "
            f"bus_id={bus_id}, route_id={route_id}"
        )

        road_network = get_road_network(route_id)

        services[bus_id] = MapMatchingService(
            road_network
        )

    return services[bus_id]


@app.get("/")
def root():
    return {
        "message": "Shuttle Map Matching Server is running"
    }


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "active_bus_count": len(services),
        "active_bus_ids": list(services.keys()),
    }


@app.post("/firebase/test")
def firebase_test():

    write_test_data()

    return {
        "status": "ok",
        "message": "Firebase test data written"
    }

@app.post("/trip/start")
def start_trip(trip: TripRequest):

    # 이미 상태가 존재하면 제거
    if trip.bus_id in services:
        del services[trip.bus_id]

    # 해당 노선의 RoadNetwork 가져오기
    road_network = get_road_network(trip.route_id)

    # 새로운 운행 상태 생성
    services[trip.bus_id] = MapMatchingService(
        road_network
    )

    start_bus_trip(
    bus_id=trip.bus_id,
    route_id=trip.route_id,
    )

    print(
        f"[TRIP START] "
        f"bus_id={trip.bus_id}, "
        f"route_id={trip.route_id}"
    )

    return {
        "status": "started",
        "bus_id": trip.bus_id,
        "route_id": trip.route_id,
    }


@app.post("/trip/end")
def end_trip(trip: TripRequest):

    if trip.bus_id not in services:
        return {
            "status": "not_active",
            "bus_id": trip.bus_id,
            "route_id": trip.route_id,
        }

    del services[trip.bus_id]

    end_bus_trip(
    bus_id=trip.bus_id,
    )

    print(
        f"[TRIP END] "
        f"bus_id={trip.bus_id}, "
        f"route_id={trip.route_id}"
    )

    return {
        "status": "ended",
        "bus_id": trip.bus_id,
        "route_id": trip.route_id,
    }


@app.post("/mapmatch")
def mapmatch(gps: GPSRequest):

    if gps.bus_id not in services:
        return {
            "status": "error",
            "message": "Trip is not active. Call /trip/start first.",
            "bus_id": gps.bus_id,
            "route_id": gps.route_id,
        }

    service = services[gps.bus_id]

    result = service.process_gps(
        bus_id=gps.bus_id,
        route_id=gps.route_id,
        lat=gps.lat,
        lon=gps.lon,
        heading=gps.heading,
        timestamp=gps.timestamp,
    )

    if result.get("matched"):

        matched = result["matched"]

        update_bus_location(
            bus_id=gps.bus_id,
            route_id=gps.route_id,
            lat=matched["lat"],
            lon=matched["lon"],
            current_node=result.get("current_node"),
            timestamp=gps.timestamp,
        )

    return result