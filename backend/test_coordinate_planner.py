
import asyncio

from app.database import SessionLocal
from app.services.journey.planner import plan_coordinate_journey


async def main():
    db = SessionLocal()

    try:
        result = await plan_coordinate_journey(
            db=db,
            origin=(36.8219, -3.3869),
            destination=(36.8250, -3.3900),
            radius_m=2000,
            candidate_limit=10,
            include_unverified_transfers=True,
        )

        print("\nCoordinate journey planning result:")
        print(f"Status: {result['status']}")

        if result.get("total_journeys") is not None:
            print(f"Journeys found: {result['total_journeys']}")

            for index, journey in enumerate(
                result["journeys"],
                start=1,
            ):
                print(f"\nJourney {index}")
                print("Board:", journey["boarding_stop"])
                print("Alight:", journey["alighting_stop"])
                print("Metrics:", journey["metrics"])
                print(
                    "Transit instructions:",
                    journey["transit"]["instructions"],
                )
        else:
            print(result["message"])

    finally:
        db.close()


asyncio.run(main())
