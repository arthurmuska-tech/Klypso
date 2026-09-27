"""Distribution strategy learned from KLYPSO publication performance."""
from collections import defaultdict
from datetime import datetime, timezone


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _performance(row):
    views = max(0.0, _num(row["views"]))
    interactions = max(0.0, _num(row["likes"])) + max(0.0, _num(row["comments"])) + max(0.0, _num(row["shares"]))
    engagement_pct = interactions / max(1.0, views) * 100.0
    engagement_signal = min(50.0, engagement_pct * 3.0)
    completion = max(0.0, min(100.0, _num(row["completion_rate"])))
    view_signal = min(100.0, views / 1000.0)
    return round(0.60 * view_signal + 0.15 * engagement_signal + 0.25 * completion, 2)


def _group(rows, key_fn):
    groups = defaultdict(list)
    for row in rows:
        key = key_fn(row)
        if key is not None:
            groups[key].append(_performance(row))
    return {
        key: {
            "samples": len(values),
            "score": round(sum(values) / len(values), 2),
        }
        for key, values in groups.items()
    }


def build_distribution_strategy(db, user_id):
    rows = db.execute(
        "SELECT m.platform,m.views,m.likes,m.comments,m.shares,m.completion_rate,"
        "m.candidate_id,m.recorded_at,q.scheduled_for "
        "FROM clip_metrics m LEFT JOIN publish_queue q ON q.id=m.queue_id "
        "WHERE m.user_id=? ORDER BY m.id DESC LIMIT 1000",
        (user_id,),
    ).fetchall()

    day_names = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
    normalized = []
    for row in rows:
        item = dict(row)
        raw = str(row["scheduled_for"] or row["recorded_at"] or "")
        dt = None
        try:
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            try:
                dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        item["_dt"] = dt
        item["_score"] = _performance(row)
        item["_day"] = day_names[dt.weekday()] if dt else None
        item["_hour"] = dt.hour if dt else None
        normalized.append(item)

    with_time = [item for item in normalized if item["_dt"] is not None]
    by_hour = _group(with_time, lambda row: row["_hour"])
    by_day = _group(with_time, lambda row: row["_day"])
    by_platform = _group(normalized, lambda row: row["platform"] or "unknown")

    best_hours = sorted(
        (
            {"hour": int(hour), **data}
            for hour, data in by_hour.items()
            if data["samples"] >= 2
        ),
        key=lambda item: (-item["score"], -item["samples"], item["hour"]),
    )[:5]
    best_days = sorted(
        (
            {"day": day, **data}
            for day, data in by_day.items()
            if data["samples"] >= 2
        ),
        key=lambda item: (-item["score"], -item["samples"]),
    )[:5]

    if not best_hours:
        best_hours = sorted(
            ({"hour": int(hour), **data} for hour, data in by_hour.items()),
            key=lambda item: (-item["score"], -item["samples"], item["hour"]),
        )[:3]
    if not best_days:
        best_days = sorted(
            ({"day": day, **data} for day, data in by_day.items()),
            key=lambda item: (-item["score"], -item["samples"]),
        )[:3]

    platform_order = sorted(
        ({"platform": platform, **data} for platform, data in by_platform.items()),
        key=lambda item: (-item["score"], -item["samples"], item["platform"]),
    )

    return {
        "engine": "klypso-distribution-dna-v1",
        "samples": len(normalized),
        "best_hours": best_hours,
        "best_days": best_days,
        "platforms": platform_order[:6],
        "confidence": round(min(1.0, len(normalized) / 30.0), 2),
        "suggested_cadence": "daily" if len(normalized) >= 10 else "3x/week" if len(normalized) >= 4 else "collect_more_data",
    }
