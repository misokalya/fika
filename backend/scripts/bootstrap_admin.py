
import argparse
import sys

from sqlalchemy import select, func

from app.database import SessionLocal
from app.models import User, UserRole, AuditLog


def bootstrap_admin(email: str) -> None:
    email = email.strip().lower()

    db = SessionLocal()

    try:
        # Lock the target account while performing the bootstrap.
        user = db.scalar(
            select(User)
            .where(User.email == email)
            .with_for_update()
        )

        if user is None:
            print("ERROR: No account found with that email.")
            return

        if not user.is_active:
            print("ERROR: The target account is inactive.")
            return

        # Refuse to bootstrap if an active administrator already exists.
        active_admin_count = db.scalar(
            select(func.count(User.id)).where(
                User.role == UserRole.ADMIN.value,
                User.is_active.is_(True),
            )
        ) or 0

        if active_admin_count > 0:
            print(
                "ERROR: An active administrator already exists. "
                "Bootstrap refused."
            )
            return

        old_role = user.role

        if old_role == UserRole.ADMIN.value:
            print("This account is already an administrator.")
            return

        user.role = UserRole.ADMIN.value

        db.add(
            AuditLog(
                actor="system bootstrap",
                action="ADMIN_BOOTSTRAPPED",
                entity_type="User",
                entity_id=user.id,
                details={
                    "email": user.email,
                    "old_role": old_role,
                    "new_role": UserRole.ADMIN.value,
                },
            )
        )

        db.commit()

        print("Administrator bootstrap successful.")
        print(f"User ID: {user.id}")
        print(f"Username: {user.username}")
        print(f"Email: {user.email}")
        print(f"Previous role: {old_role}")
        print(f"New role: {user.role}")

    except Exception:
        db.rollback()
        print("ERROR: Bootstrap failed. No changes were committed.")
        raise

    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Bootstrap the first FIKA administrator."
    )

    parser.add_argument(
        "--email",
        required=True,
        help="Email address of the existing account to promote.",
    )

    args = parser.parse_args()

    try:
        bootstrap_admin(args.email)
    except Exception as exc:
        print(f"Bootstrap error: {exc}")
        sys.exit(1)
