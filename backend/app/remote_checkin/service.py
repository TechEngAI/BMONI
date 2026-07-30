from datetime import datetime, timezone
from math import atan2, cos, radians, sin, sqrt
from typing import Any

import httpx

from app.database import get_supabase
from app.errors import AppError

IP_API_URL = "http://ip-api.com/json/{}"
IP_API_TIMEOUT_SECONDS = 3

IMPOSSIBLE_TRAVEL_SPEED_KMH_THRESHOLD = 900


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6_371.0
    phi1, phi2 = radians(lat1), radians(lat2)
    delta_phi = radians(lat2 - lat1)
    delta_lambda = radians(lng2 - lng1)
    a = sin(delta_phi / 2) ** 2 + cos(phi1) * cos(phi2) * sin(delta_lambda / 2) ** 2
    return radius * 2 * atan2(sqrt(a), sqrt(1 - a))


async def lookup_ip_geolocation(ip_address: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=IP_API_TIMEOUT_SECONDS) as client:
            resp = await client.get(IP_API_URL.format(ip_address))
            data = resp.json()
    except Exception:
        return None
    if data.get("status") != "success":
        return None
    return {
        "geo_lat": data.get("lat"),
        "geo_lng": data.get("lon"),
        "geo_city": data.get("city"),
        "geo_country": data.get("country"),
    }


async def check_in(
    worker: dict[str, Any],
    device_fingerprint: str,
    ip_address: str,
) -> dict[str, Any]:
    db = get_supabase()
    now = datetime.now(timezone.utc)

    recent = (
        db.table("remote_checkins")
        .select("checked_in_at")
        .eq("worker_id", worker["id"])
        .order("checked_in_at", desc=True)
        .limit(1)
        .execute()
        .data
    )
    if recent:
        last_time = datetime.fromisoformat(recent[0]["checked_in_at"].replace("Z", "+00:00"))
        if (now - last_time).total_seconds() < 60:
            raise AppError(429, "RATE_LIMITED", "You can only check in once every 60 seconds.")

    geo = await lookup_ip_geolocation(ip_address)

    insert_data = {
        "worker_id": worker["id"],
        "checked_in_at": now.isoformat(),
        "ip_address": ip_address,
        "device_fingerprint": device_fingerprint,
        "geo_lat": geo["geo_lat"] if geo else None,
        "geo_lng": geo["geo_lng"] if geo else None,
        "geo_city": geo["geo_city"] if geo else None,
        "geo_country": geo["geo_country"] if geo else None,
    }

    result = db.table("remote_checkins").insert(insert_data).execute()
    rows = result.data
    if not rows:
        raise AppError(500, "DATABASE_INSERT_FAILED", "Could not record check-in. Please try again.")
    record = rows[0] if isinstance(rows, list) else rows

    return {
        "id": record["id"],
        "timestamp": record["checked_in_at"],
    }


async def calculate_impossible_travel(worker_id: str) -> dict[str, Any]:
    rows = (
        get_supabase()
        .table("remote_checkins")
        .select("*")
        .eq("worker_id", worker_id)
        .order("checked_in_at", desc=True)
        .limit(2)
        .execute()
        .data
    )

    if len(rows) < 2:
        return {
            "impossible_travel": False,
            "distance_km": 0.0,
            "implied_speed_kmh": 0.0,
            "reason": "insufficient_checkins",
        }

    first, second = rows[0], rows[1]

    if first.get("geo_lat") is None or first.get("geo_lng") is None or second.get("geo_lat") is None or second.get("geo_lng") is None:
        return {
            "impossible_travel": False,
            "distance_km": 0.0,
            "implied_speed_kmh": 0.0,
            "reason": "insufficient_geo_data",
        }

    distance_km = haversine_km(
        float(first["geo_lat"]), float(first["geo_lng"]),
        float(second["geo_lat"]), float(second["geo_lng"]),
    )

    t1 = datetime.fromisoformat(first["checked_in_at"].replace("Z", "+00:00"))
    t2 = datetime.fromisoformat(second["checked_in_at"].replace("Z", "+00:00"))
    time_hours = abs((t1 - t2).total_seconds()) / 3600

    if time_hours <= 0:
        return {
            "impossible_travel": True,
            "distance_km": round(distance_km, 2),
            "implied_speed_kmh": float("inf"),
            "reason": "zero_or_negative_time_gap",
        }

    implied_speed_kmh = distance_km / time_hours
    impossible = implied_speed_kmh > IMPOSSIBLE_TRAVEL_SPEED_KMH_THRESHOLD

    return {
        "impossible_travel": impossible,
        "distance_km": round(distance_km, 2),
        "implied_speed_kmh": round(implied_speed_kmh, 2),
        "reason": "exceeded_speed_threshold" if impossible else None,
    }
