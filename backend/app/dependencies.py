
from collections.abc import Generator

from sqlalchemy.orm import Session

from app.database import SessionLocal


def get_db() -> Generator[Session, None, None]:
    """
    Provide a database session for an API request.

    The session is automatically closed after the request,
    including when an exception occurs.
    """
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
