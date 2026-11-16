from app.database import SessionLocal
from app.services.journey.nearby_stops import find_nearby_stops


# Approximate Arusha Clock Tower coordinates.
longitude = 36.8219
latitude = -3.3869

db = SessionLocal()

try:
    stops = find_nearby_stops(
        db=db,
        longitude=longitude,
        latitude=latitude,
        radius_m=2000,
        limit=20,
    )

    print("\nNearby dala-dala stops:")

    for stop in stops:
        print(stop)

    print(f"\nTotal stops found: {len(stops)}")

finally:
    db.close()