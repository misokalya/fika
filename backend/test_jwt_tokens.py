
from app.services.auth.tokens import create_access_token
import jwt
import os

def test_access_token_generation():
    token = create_access_token(
        user_id=1,
        role="passenger",
    )

    decoded = jwt.decode(
        token,
        os.getenv("JWT_SECRET_KEY"),
        algorithms=["HS256"],
    )

    assert decoded["sub"] == "1"
    assert decoded["role"] == "passenger"
    assert decoded["type"] == "access"
    assert "exp" in decoded

    print("JWT access-token test passed.")

if __name__ == "__main__":
    test_access_token_generation()