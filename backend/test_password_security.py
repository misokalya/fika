
from app.services.auth.security import hash_password, verify_password


def test_password_hashing():
    password = "FikaSecurePassword123!"

    hashed = hash_password(password)

    assert hashed != password
    assert verify_password(password, hashed)
    assert not verify_password("WrongPassword123!", hashed)

    print("Password hashing test passed.")


if __name__ == "__main__":
    test_password_hashing()
