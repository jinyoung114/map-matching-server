from pathlib import Path

import firebase_admin
from firebase_admin import credentials, db


BASE_DIR = Path(__file__).resolve().parent.parent

SERVICE_ACCOUNT_PATH = (
    BASE_DIR / "firebase" / "firebase-service-account.json"
)

DATABASE_URL = (
    "https://shuttlebusapp-ce380-default-rtdb."
    "asia-southeast1.firebasedatabase.app"
)


def initialize_firebase():

    if not firebase_admin._apps:
        cred = credentials.Certificate(
            str(SERVICE_ACCOUNT_PATH)
        )

        firebase_admin.initialize_app(
            cred,
            {
                "databaseURL": DATABASE_URL
            }
        )

        print("[FIREBASE] initialized")


def write_test_data():

    initialize_firebase()

    ref = db.reference("test_connection")

    ref.set({
        "status": "connected",
        "message": "FastAPI Firebase connection success"
    })

    print("[FIREBASE] test data written")


def update_bus_location(
    bus_id: str,
    route_id: str,
    lat: float,
    lon: float,
    current_node,
    timestamp: str,
):

    initialize_firebase()

    ref = db.reference(f"busLocations/{bus_id}")

    ref.set({
        "bus_id": bus_id,
        "route_id": route_id,
        "lat": lat,
        "lon": lon,
        "current_node": current_node,
        "timestamp": timestamp,
        "trip_active": True,
    })

    print(
        f"[FIREBASE] bus location updated "
        f"bus_id={bus_id}, route_id={route_id}"
    )


def start_bus_trip(
    bus_id: str,
    route_id: str,
):
    initialize_firebase()

    ref = db.reference(f"busLocations/{bus_id}")

    ref.set({
        "bus_id": bus_id,
        "route_id": route_id,
        "trip_active": True,
    })

    print(
        f"[FIREBASE] trip started "
        f"bus_id={bus_id}, route_id={route_id}"
    )


def end_bus_trip(
    bus_id: str,
):
    initialize_firebase()

    ref = db.reference(f"busLocations/{bus_id}")

    ref.delete()

    print(
        f"[FIREBASE] trip ended "
        f"bus_id={bus_id}"
    )