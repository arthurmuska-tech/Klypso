"""KLYPSO chat intelligence helpers.

Accepts normalized chat messages from Twitch/Kick/YouTube exports or connector
adapters and turns bursts of audience activity into timestamped evidence.
"""
import re
from collections import Counter


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def normalize_chat_messages(messages, limit=5000):
    normalized = []
    for raw in (messages or [])[:limit]:
        if not isinstance(raw, dict):
            continue
        timestamp = _num(
            raw.get("timestamp", raw.get("time", raw.get("start", raw.get("offset", 0))))
        )
        text = " ".join(str(raw.get("text", raw.get("message", "")) or "").split())
        if not text:
            continue
        author = " ".join(str(raw.get("author", raw.get("user", "")) or "").split())[:80]
        normalized.append({
            "timestamp": max(0.0, timestamp),
            "text": text[:500],
            "author": author,
            "emotes": list(raw.get("emotes") or [])[:12],
        })
    return sorted(normalized, key=lambda item: item["timestamp"])


def build_chat_signals(messages, bin_seconds=5.0):
    data = normalize_chat_messages(messages)
    if not data:
        return {
            "engine": "klypso-chat-v1",
            "message_count": 0,
            "unique_authors": 0,
            "events": [],
            "spikes": [],
            "top_terms": [],
        }

    buckets = Counter()
    authors = set()
    term_counter = Counter()
    for item in data:
        bucket = int(item["timestamp"] // max(1.0, bin_seconds))
        buckets[bucket] += 1
        if item["author"]:
            authors.add(item["author"].lower())
        for token in re.findall(r"[A-Za-zÀ-ÿ0-9]{3,}", item["text"].lower()):
            if token not in {"the", "and", "que", "les", "des", "une", "pour", "avec"}:
                term_counter[token] += 1

    counts = list(buckets.values())
    baseline = sum(counts) / max(1, len(counts))
    threshold = max(5.0, baseline * 2.2)
    spikes = []
    for bucket, count in sorted(buckets.items()):
        if count >= threshold:
            start = bucket * bin_seconds
            spikes.append({
                "start": round(start, 3),
                "end": round(start + bin_seconds, 3),
                "messages": count,
                "intensity": round(min(1.0, count / max(threshold, 1.0)), 3),
            })

    events = []
    for spike in spikes:
        events.append({
            "start": round(spike["start"] - 5.0, 3),
            "end": round(spike["end"] + 8.0, 3),
            "source": "chat_spike",
            "messages": spike["messages"],
            "intensity": spike["intensity"],
        })

    hot_messages = []
    if spikes:
        for item in data:
            if any(spike["start"] <= item["timestamp"] <= spike["end"] for spike in spikes):
                hot_messages.append(item)
                if len(hot_messages) >= 40:
                    break

    return {
        "engine": "klypso-chat-v1",
        "message_count": len(data),
        "unique_authors": len(authors),
        "events": events[:120],
        "spikes": spikes[:120],
        "top_terms": [{"term": term, "count": count} for term, count in term_counter.most_common(15)],
        "hot_messages": hot_messages,
    }


def enrich_candidates_with_chat_signals(candidates, chat_signals):
    signals = chat_signals or {}
    events = signals.get("events") or []
    total_messages = max(1, int(signals.get("message_count", 0)))
    enriched = []
    for candidate in candidates or []:
        item = dict(candidate)
        start = _num(candidate.get("start"))
        end = _num(candidate.get("end"), start)
        overlap = 0.0
        matched_messages = 0
        max_intensity = 0.0
        for event in events:
            left = max(start, _num(event.get("start")))
            right = min(end, _num(event.get("end")))
            if right > left:
                overlap += right - left
                matched_messages += int(event.get("messages", 0) or 0)
                max_intensity = max(max_intensity, _num(event.get("intensity")))
        chat_signal = min(1.0, 0.65 * overlap / max(8.0, end - start) + 0.35 * max_intensity)
        item["chat_spike"] = round(chat_signal, 3)
        item["chat_messages"] = min(total_messages, matched_messages)
        item["chat_signal_score"] = round(chat_signal * 100.0, 1)
        enriched.append(item)
    return enriched
