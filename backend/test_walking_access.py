import asyncio

from app.database import SessionLocal
from app.services.journey.access import find_walking_access_routes


async def main():
    db = SessionLocal()

    try:
        results = await find_walking_access_routes(
            db=db,
            longitude=36.8219,
            latitude=-3.3869,
            radius_m=2000,
            limit=10,
        )

        print("\nWalking access routes:")

        for result in results:
            print({
                "stop_id": result["id"],
                "stop_name": result["name"],
                "straight_line_distance_m": result["distance_m"],
                "routing_status": result["routing_status"],
                "walking_distance_km": result.get(
                    "walking_distance_km"
                ),
                "walking_duration_minutes": result.get(
                    "walking_duration_minutes"
                ),
                "routing_error": result.get("routing_error"),
            })

        print(f"\nTotal candidates: {len(results)}")

    finally:
        db.close()


asyncio.run(main())