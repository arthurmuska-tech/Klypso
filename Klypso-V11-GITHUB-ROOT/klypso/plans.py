from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

@dataclass(frozen=True)
class Plan:
    key: str
    name: str
    monthly_price_eur: int
    clips_per_month: int
    max_projects: int
    max_upload_mb: int
    advanced_ai: bool
    studio: bool
    batch: bool

PLANS = {
    "free": Plan("free", "Free", 0, 5, 2, 512, False, False, False),
    "pro": Plan("pro", "Pro", 12, 100, 20, 2048, True, False, True),
    "ultra": Plan("ultra", "Ultra", 30, 500, 100, 4096, True, True, True),
}

# New accounts receive a single server-side trial of Pro for 10 days.
TRIAL_DAYS = 10
TRIAL_PLAN = "pro"


def get_plan(key):
    return PLANS.get(key, PLANS["free"])


def _parse_datetime(value):
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def trial_ends_at(started_at):
    value = _parse_datetime(started_at)
    return value + timedelta(days=TRIAL_DAYS) if value else None


def trial_active(started_at, now=None):
    end = trial_ends_at(started_at)
    if not end:
        return False
    now = now or datetime.now(timezone.utc)
    return now < end


def promo_ends_at(started_at, duration_weeks):
    value = _parse_datetime(started_at)
    if not value:
        return None
    if not isinstance(duration_weeks, int) or duration_weeks < 1 or duration_weeks > 52:
        raise ValueError("La durée d'un code promo doit être comprise entre 1 et 52 semaines.")
    return value + timedelta(weeks=duration_weeks)


def promo_active(started_at, duration_weeks, now=None):
    end = promo_ends_at(started_at, duration_weeks)
    if not end:
        return False
    now = now or datetime.now(timezone.utc)
    return now < end


def monthly_clip_quota_reached(used, plan_key):
    return used >= get_plan(plan_key).clips_per_month
