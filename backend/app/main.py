from fastapi import FastAPI
from datetime import datetime, timezone
from sqlalchemy import text
from app.database import engine
from app.routers import (
    routes,
    stops,
    route_stops,
    transfers,
    journeys,
    auth,
)
from app.routers import audit_logs
from app.routers import (
    routes,
    stops,
    route_stops,
    transfers,
    journeys,
    auth,
    fares,
)


app = FastAPI(
    title="FIKA API",
    description="Intelligent Multimodal Route Navigation System for Tanzania",
    version="0.1.0"
)

app.include_router(routes.router)
app.include_router(stops.router)
app.include_router(route_stops.router)
app.include_router(transfers.router)
app.include_router(journeys.router)
app.include_router(auth.router)
app.include_router(audit_logs.router)
app.include_router(fares.router)

@app.get("/")
def root():
    return {
        "application": "FIKA",
        "message": "Welcome to the FIKA API",
        "version": "0.1.0"
    }


@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "fika-api",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

@app.get("/health/db")
def database_health_check():
    try:
        with engine.connect() as connection:
            result = connection.execute(
                text("""
                    SELECT
                        PostGIS_Full_Version() AS postgis,
                        current_database() AS database
                """)
            ).mappings().first()

            return {
                "status": "connected",
                "database": result["database"],
                "postgis": result["postgis"]
            }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e)
        }