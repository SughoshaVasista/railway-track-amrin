"""AMRIN backend management commands."""

import argparse
import json
from getpass import getpass
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.config import Settings
from app.db.session import build_engine, build_session_factory
from app.models import Device, User
from app.schemas.auth import CreateAdminRequest
from app.services.demo_seed import seed_demo
from app.security.passwords import hash_password


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["seed-demo", "create-admin", "register-device", "reset-password"])
    parser.add_argument("--device-id", help="Device identifier used by an ESP32 client")
    parser.add_argument("--device-name", help="Human-readable device name")
    parser.add_argument("--platform", default="ESP32-CAM")
    parser.add_argument("--city")
    parser.add_argument("--target", help="Exact account username, email, or display name for password reset")
    parser.add_argument("--json-file", help="JSON file containing first-admin name, email, username, and password")
    parser.add_argument("--additional-admin", action="store_true", help="Create another admin using this local CLI")
    args = parser.parse_args()

    engine = build_engine(Settings().database_url)
    session_factory = build_session_factory(engine)
    try:
        if args.command == "seed-demo":
            with session_factory.begin() as session:
                counts = seed_demo(session)
            inserted = sum(counts.values())
            print(f"Demo seed complete: {inserted} records inserted across {len(counts)} record types.")
        elif args.command == "create-admin":
            _create_admin(session_factory, args.json_file, args.additional_admin)
        elif args.command == "reset-password":
            _reset_password(session_factory, args.target)
        else:
            _register_device(session_factory, args.device_id, args.device_name, args.platform, args.city)
    finally:
        engine.dispose()


def _create_admin(session_factory, json_file: str | None = None, additional_admin: bool = False) -> None:
    if not additional_admin:
        with session_factory() as session:
            if session.scalar(select(User.id).where(User.role == "admin", User.source != "demo")):
                raise SystemExit("An administrator already exists; use --additional-admin for another local admin.")
    if json_file:
        try:
            payload = json.loads(Path(json_file).read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("JSON root must be an object")
            name, email, username, password = (payload[key] for key in ("name", "email", "username", "password"))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise SystemExit(f"Could not read admin JSON: {exc}") from exc
    else:
        print("Create the first AMRIN administrator. The password will not be displayed.")
        name = input("Name: ").strip()
        email = input("Email: ").strip().lower()
        username = input("Username: ").strip().lower()
        password = getpass("Password (12+ characters): ")
        confirmation = getpass("Confirm password: ")
        if password != confirmation:
            raise SystemExit("Passwords did not match.")
    try:
        values = CreateAdminRequest(name=name, email=email, username=username, password=password)
    except ValidationError as exc:
        raise SystemExit(f"Invalid administrator details: {exc}") from exc

    with session_factory.begin() as session:
        if not additional_admin and session.scalar(select(User.id).where(User.role == "admin", User.source != "demo")):
            raise SystemExit("An administrator already exists; use --additional-admin for another local admin.")
        user = User(
            id=f"USER-{uuid4().hex}",
            name=values.name.strip(),
            email=str(values.email).strip().lower(),
            username=values.username.strip().lower(),
            password_hash=hash_password(values.password),
            role="admin",
            approval_status="approved",
            city=None,
            worker_id=None,
            is_active=True,
            source="cli",
        )
        session.add(user)
        try:
            session.flush()
        except IntegrityError as exc:
            raise SystemExit("That email or username is already in use.") from exc
    print(f"Administrator account created for {values.email}.")


def _reset_password(session_factory, target: str | None) -> None:
    normalized = (target or "").strip().lower()
    if not normalized:
        raise SystemExit("Usage: python -m app.cli reset-password --target matt_hagen")

    with session_factory() as session:
        matches = session.scalars(select(User).where(or_(
            func.lower(User.username) == normalized,
            func.lower(User.email) == normalized,
            func.lower(User.name) == normalized,
        ))).all()
        if not matches:
            raise SystemExit("No account matched that exact username, email, or display name.")
        if len(matches) != 1:
            raise SystemExit("More than one account matched. Use the account's exact username or email.")
        account_id = matches[0].id
        print(f"Target account: {matches[0].name} ({matches[0].role}, {matches[0].id})")

    password = getpass("New password (10+ characters): ")
    confirmation = getpass("Confirm new password: ")
    if password != confirmation:
        raise SystemExit("Passwords did not match; no changes made.")
    if len(password) < 10 or len(password) > 256:
        raise SystemExit("Password must be between 10 and 256 characters; no changes made.")

    with session_factory.begin() as session:
        account = session.get(User, account_id)
        if account is None:
            raise SystemExit("The target account no longer exists; no changes made.")
        account.password_hash = hash_password(password)
        account.auth_version += 1
    print("Password updated. The new password was not displayed or saved by this command.")


def _register_device(session_factory, device_id: str | None, name: str | None, platform: str, city: str | None) -> None:
    device_id = (device_id or "").strip()
    name = (name or "").strip()
    if not device_id or not name:
        raise SystemExit("Usage: python -m app.cli register-device --device-id esp32-cam-01 --device-name 'Rail camera'")
    with session_factory.begin() as session:
        if session.get(Device, device_id) is not None:
            print(f"Device {device_id} is already registered; no changes made.")
            return
        session.add(Device(
            id=device_id,
            name=name,
            platform=platform.strip() or "ESP32-CAM",
            city=city.strip().lower() if city else None,
            status="UNKNOWN",
            network_status="UNKNOWN",
            source="hardware",
        ))
    print(f"Registered device {device_id} ({platform}).")


if __name__ == "__main__":
    main()
