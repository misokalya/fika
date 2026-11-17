
from pwdlib import PasswordHash

# Argon2id is the password hashing algorithm.
password_hash = PasswordHash.recommended()


def hash_password(password: str) -> str:
    """Hash a plain-text password before storing it."""
    if not password:
        raise ValueError("Password cannot be empty.")

    return password_hash.hash(password)


def verify_password(
    plain_password: str,
    hashed_password: str,
) -> bool:
    """Verify a password against its stored hash."""
    if not plain_password or not hashed_password:
        return False

    return password_hash.verify(plain_password, hashed_password)
