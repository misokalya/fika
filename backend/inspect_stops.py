from sqlalchemy import text
from app.database import SessionLocal

db = SessionLocal()

try:
    result = db.execute(text("""
        SELECT
            s.id,
            s.name,
            s.is_active,
            s.is_verified,
            ST_X(s.location) AS longitude,
            ST_Y(s.location) AS latitude,
            COUNT(DISTINCT r.id) AS active_route_count
        FROM stops s
        LEFT JOIN route_stops rs ON rs.stop_id = s.id
        LEFT JOIN routes r
            ON r.id = rs.route_id
            AND r.is_active = TRUE
        GROUP BY s.id
        ORDER BY s.id;
    """)).mappings().all()

    for stop in result:
        print(dict(stop))

    print(f"\nTotal stops: {len(result)}")

finally:
    db.close()