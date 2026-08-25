"""Accounts, households and memberships.

The shared-PIN build had one household and no notion of a person. A hosted
product needs both: an account is personal, a household is shared, and a
membership joins the two. Access is decided in exactly one place — a
membership row — so a "join request" is simply a membership that is still
``pending``.

Nothing here trusts a client-supplied household id. Every lookup goes through
:func:`membership_for`, which is what keeps one household's receipts out of
another's reach.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import datetime

from argon2 import PasswordHasher
from argon2.exceptions import (
    InvalidHashError,
    VerificationError,
    VerifyMismatchError,
)
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import (
    Household,
    HouseholdMembership,
    MembershipRole,
    MembershipStatus,
    User,
    utc_now,
)

MINIMUM_PASSWORD_LENGTH = 10
MAXIMUM_PASSWORD_LENGTH = 200

# Deliberately loose: the mail server decides what is deliverable. This only
# rejects what obviously cannot be an address.
_EMAIL = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")

_PASSWORD_HASHER = PasswordHasher(
    time_cost=3,
    memory_cost=64 * 1024,
    parallelism=2,
)

# Unambiguous alphabet: no O/0 or I/1, because these codes get read aloud.
_JOIN_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class AccountError(Exception):
    """An account operation a person can correct."""

    def __init__(self, code: str, message: str, *, status_code: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def normalize_email(value: str) -> str:
    email = (value or "").strip().lower()
    if not _EMAIL.match(email) or len(email) > 320:
        raise AccountError("INVALID_EMAIL", "Enter a valid email address.")
    return email


def validate_password(value: str) -> str:
    if not isinstance(value, str):
        raise AccountError("INVALID_PASSWORD", "Enter a password.")
    if not MINIMUM_PASSWORD_LENGTH <= len(value) <= MAXIMUM_PASSWORD_LENGTH:
        raise AccountError(
            "INVALID_PASSWORD",
            f"Use a password of at least {MINIMUM_PASSWORD_LENGTH} characters.",
        )
    return value


def hash_password(value: str) -> str:
    return _PASSWORD_HASHER.hash(validate_password(value))


def verify_password(password_hash: str, candidate: str) -> bool:
    try:
        return _PASSWORD_HASHER.verify(password_hash, candidate)
    except (
        InvalidHashError,
        VerificationError,
        VerifyMismatchError,
        TypeError,
        ValueError,
    ):
        return False


def generate_join_code() -> str:
    """A short, non-secret code identifying a household.

    It is an identifier, not a credential: holding it lets someone *ask* to
    join, never join.
    """

    return "-".join(
        "".join(secrets.choice(_JOIN_CODE_ALPHABET) for _ in range(4))
        for _ in range(2)
    )


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------


def register_user(
    session: Session,
    *,
    email: str,
    password: str,
    display_name: str | None = None,
) -> User:
    """Create an account. Fails if the address is already registered."""

    address = normalize_email(email)
    validate_password(password)
    existing = session.scalar(select(User).where(User.email == address))
    if existing is not None:
        # Deliberately explicit. Hiding this makes the form unusable, and the
        # address is already discoverable through the reset flow.
        raise AccountError(
            "EMAIL_TAKEN",
            "That email address already has an account. Try signing in.",
            status_code=409,
        )
    user = User(
        email=address,
        password_hash=hash_password(password),
        display_name=(display_name or "").strip() or address.split("@")[0],
    )
    session.add(user)
    session.flush()
    return user


def authenticate_user(session: Session, *, email: str, password: str) -> User:
    """Check an email and password.

    The same message covers an unknown address and a wrong password, so this
    cannot be used to enumerate who has an account.
    """

    try:
        address = normalize_email(email)
    except AccountError:
        raise AccountError(
            "INVALID_CREDENTIALS",
            "That email or password is not right.",
            status_code=401,
        ) from None

    user = session.scalar(select(User).where(User.email == address))
    if user is None or not verify_password(user.password_hash, password):
        raise AccountError(
            "INVALID_CREDENTIALS",
            "That email or password is not right.",
            status_code=401,
        )
    return user


def delete_user(session: Session, user: User) -> None:
    """Delete an account and its memberships.

    Household ledgers survive: receipts belong to the household, not to the
    person who photographed them.
    """

    session.delete(user)
    session.flush()


# ---------------------------------------------------------------------------
# Households and membership
# ---------------------------------------------------------------------------


def create_household(session: Session, *, owner: User, name: str) -> Household:
    display_name = (name or "").strip()
    if not display_name:
        raise AccountError("INVALID_NAME", "Give your household a name.")

    household = Household(display_name=display_name[:100])
    for _ in range(8):
        candidate = generate_join_code()
        if session.scalar(
            select(func.count())
            .select_from(Household)
            .where(Household.join_code == candidate)
        ):
            continue
        household.join_code = candidate
        break
    session.add(household)
    session.flush()

    session.add(
        HouseholdMembership(
            household_id=household.id,
            user_id=owner.id,
            role=MembershipRole.OWNER,
            status=MembershipStatus.ACTIVE,
            decided_at=utc_now(),
        )
    )
    session.flush()
    return household


def memberships_for(session: Session, user: User) -> list[HouseholdMembership]:
    """Every membership and outstanding request this account holds."""

    return list(
        session.scalars(
            select(HouseholdMembership)
            .where(HouseholdMembership.user_id == user.id)
            .where(HouseholdMembership.status != MembershipStatus.DECLINED)
            .order_by(HouseholdMembership.created_at)
        )
    )


def membership_for(
    session: Session,
    *,
    user: User,
    household_id: int,
    require_active: bool = True,
) -> HouseholdMembership:
    """This account's membership of one household, or a 404.

    A household someone is not in is reported as *not found* rather than
    *forbidden*, so the API does not confirm that it exists.
    """

    membership = session.scalar(
        select(HouseholdMembership)
        .where(HouseholdMembership.user_id == user.id)
        .where(HouseholdMembership.household_id == household_id)
    )
    if membership is None or (
        require_active and membership.status is not MembershipStatus.ACTIVE
    ):
        raise AccountError(
            "HOUSEHOLD_NOT_FOUND",
            "That household is not available to this account.",
            status_code=404,
        )
    return membership


def resolve_household(session: Session, reference: str) -> Household:
    """Find a household by join code or numeric id."""

    code = (reference or "").strip().upper()
    household = session.scalar(select(Household).where(Household.join_code == code))
    if household is None and reference.strip().isdigit():
        household = session.get(Household, int(reference.strip()))
    if household is None:
        raise AccountError(
            "HOUSEHOLD_NOT_FOUND",
            "No household matches that ID. Check it with whoever shared it.",
            status_code=404,
        )
    return household


def request_to_join(
    session: Session,
    *,
    user: User,
    household: Household,
) -> HouseholdMembership:
    """Ask to join. This creates a request, never access."""

    existing = session.scalar(
        select(HouseholdMembership)
        .where(HouseholdMembership.user_id == user.id)
        .where(HouseholdMembership.household_id == household.id)
    )
    if existing is not None:
        if existing.status is MembershipStatus.ACTIVE:
            raise AccountError(
                "ALREADY_MEMBER",
                "You are already in that household.",
                status_code=409,
            )
        # A previously declined request may be made again.
        existing.status = MembershipStatus.PENDING
        existing.decided_at = None
        session.flush()
        return existing

    membership = HouseholdMembership(
        household_id=household.id,
        user_id=user.id,
        role=MembershipRole.MEMBER,
        status=MembershipStatus.PENDING,
    )
    session.add(membership)
    session.flush()
    return membership


def cancel_request(session: Session, *, user: User, household_id: int) -> None:
    membership = membership_for(
        session,
        user=user,
        household_id=household_id,
        require_active=False,
    )
    if membership.status is MembershipStatus.ACTIVE:
        raise AccountError(
            "ALREADY_MEMBER",
            "You are a member of that household, not a requester.",
            status_code=409,
        )
    session.delete(membership)
    session.flush()


def require_admin(membership: HouseholdMembership) -> None:
    if membership.role not in (MembershipRole.OWNER, MembershipRole.ADMIN):
        raise AccountError(
            "NOT_PERMITTED",
            "Only an owner or admin can manage who is in this household.",
            status_code=403,
        )


def household_members(
    session: Session,
    household_id: int,
) -> list[tuple[HouseholdMembership, User]]:
    rows = session.execute(
        select(HouseholdMembership, User)
        .join(User, User.id == HouseholdMembership.user_id)
        .where(HouseholdMembership.household_id == household_id)
        .where(HouseholdMembership.status != MembershipStatus.DECLINED)
        .order_by(HouseholdMembership.created_at)
    ).all()
    return [(membership, user) for membership, user in rows]


def resolve_request(
    session: Session,
    *,
    household_id: int,
    membership_id: str,
    approve: bool,
) -> HouseholdMembership:
    membership = session.get(HouseholdMembership, membership_id)
    if membership is None or membership.household_id != household_id:
        raise AccountError(
            "REQUEST_NOT_FOUND",
            "That request is no longer waiting.",
            status_code=404,
        )
    if membership.status is not MembershipStatus.PENDING:
        raise AccountError(
            "ALREADY_DECIDED",
            "Someone has already answered that request.",
            status_code=409,
        )
    membership.status = (
        MembershipStatus.ACTIVE if approve else MembershipStatus.DECLINED
    )
    membership.decided_at = utc_now()
    session.flush()
    return membership


def remove_member(
    session: Session,
    *,
    household_id: int,
    membership_id: str,
) -> None:
    membership = session.get(HouseholdMembership, membership_id)
    if membership is None or membership.household_id != household_id:
        raise AccountError(
            "MEMBER_NOT_FOUND",
            "That person is not in this household.",
            status_code=404,
        )
    if membership.role is MembershipRole.OWNER:
        raise AccountError(
            "CANNOT_REMOVE_OWNER",
            "A household keeps its owner. Transfer ownership first.",
            status_code=409,
        )
    session.delete(membership)
    session.flush()


@dataclass(frozen=True, slots=True)
class HouseholdView:
    """What the client is told about one household."""

    id: int
    name: str
    join_code: str | None
    role: str
    status: str
    member_count: int


def household_view(
    session: Session,
    membership: HouseholdMembership,
) -> HouseholdView:
    household = session.get(Household, membership.household_id)
    name = household.display_name if household is not None else "Household"
    count = (
        session.scalar(
            select(func.count())
            .select_from(HouseholdMembership)
            .where(HouseholdMembership.household_id == membership.household_id)
            .where(HouseholdMembership.status == MembershipStatus.ACTIVE)
        )
        or 0
    )
    return HouseholdView(
        id=membership.household_id,
        name=name,
        # The code is only shown to people already inside, so it cannot be
        # harvested by anyone who is merely asking.
        join_code=(
            household.join_code
            if household is not None
            and membership.status is MembershipStatus.ACTIVE
            else None
        ),
        role=membership.role.value,
        status=membership.status.value,
        member_count=count,
    )


def verified_at(user: User) -> datetime | None:
    return user.email_verified_at


__all__ = [
    "AccountError",
    "HouseholdView",
    "authenticate_user",
    "cancel_request",
    "create_household",
    "delete_user",
    "generate_join_code",
    "hash_password",
    "household_members",
    "household_view",
    "membership_for",
    "memberships_for",
    "normalize_email",
    "register_user",
    "remove_member",
    "request_to_join",
    "require_admin",
    "resolve_household",
    "resolve_request",
    "validate_password",
    "verify_password",
]
