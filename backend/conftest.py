
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session


# ---------------------------------------------------------
# 1. Load environment and select the dedicated test DB
# ---------------------------------------------------------

BACKEND_DIR = Path(__file__).resolve().parent
ENV_FILE = BACKEND_DIR / ".env"

load_dotenv(ENV_FILE)

test_database_url = os.getenv("FIKA_TEST_DATABASE_URL")

if not test_database_url:
    raise RuntimeError(
        "FIKA_TEST_DATABASE_URL is missing from the backend .env file."
    )

parsed_url = make_url(test_database_url)

if parsed_url.database != "fika_test_db":
    raise RuntimeError(
        "Refusing to run tests: FIKA_TEST_DATABASE_URL must target "
        "'fika_test_db'."
    )

# Ensure application imports and Alembic use the test database.
os.environ["DATABASE_URL"] = test_database_url


# ---------------------------------------------------------
# 2. Create and verify the test database engine
# ---------------------------------------------------------

test_engine = create_engine(
    test_database_url,
    pool_pre_ping=True,
)

try:
    with test_engine.connect() as connection:
        database_name = connection.execute(
            text("SELECT current_database()")
        ).scalar_one()

        if database_name != "fika_test_db":
            raise RuntimeError(
                f"Expected fika_test_db, connected to {database_name!r}."
            )

except Exception:
    test_engine.dispose()
    raise


# ---------------------------------------------------------
# 3. Apply migrations to the test database
# ---------------------------------------------------------

alembic_cfg = Config(str(BACKEND_DIR / "alembic.ini"))

command.upgrade(alembic_cfg, "head")


# ---------------------------------------------------------
# 4. Database session fixture
# ---------------------------------------------------------

@pytest.fixture
def db_session():
    """
    Give a test an isolated database transaction.

    Application code can call commit(), while the outer
    transaction is rolled back when the test finishes.
    """

    connection = test_engine.connect()
    outer_transaction = connection.begin()

    session = Session(
        bind=connection,
        autoflush=False,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        session.close()

        if outer_transaction.is_active:
            outer_transaction.rollback()

        connection.close()


# ---------------------------------------------------------
# 5. FastAPI test client using the isolated DB session
# ---------------------------------------------------------

@pytest.fixture
def db_client(db_session):
    """
    TestClient that uses the isolated database session.
    """

    from fastapi.testclient import TestClient

    from app.dependencies import get_db
    from app.main import app

    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------
# 6. Cleanup test-owned authentication data
# ---------------------------------------------------------

@pytest.fixture
def clean_auth_tables(db_session):
    """
    Clear authentication and audit data for tests that
    explicitly request a clean database state.
    """

    db_session.execute(
        text("TRUNCATE TABLE audit_logs, users RESTART IDENTITY CASCADE")
    )
    db_session.flush()

    yield


@pytest.fixture
def clean_transport_tables(db_session):
    """
    Clear transport records for tests that explicitly request
    an empty route/stop dataset.
    """

    db_session.execute(
        text(
            "TRUNCATE TABLE routes, stops "
            "RESTART IDENTITY CASCADE"
        )
    )
    db_session.flush()