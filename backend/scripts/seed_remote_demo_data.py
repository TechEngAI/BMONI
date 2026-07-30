"""
Seed demo remote workers + check-in history for the remote-worker fraud detection feature.

Creates 12 synthetic remote workers with realistic check-in patterns so the
batch Isolation Forest risk-scoring pipeline has a real population to score
during hackathon judging.

Idempotent-safe: skips if "DEMO_" prefixed workers already exist.

Usage:
    python -m scripts.seed_remote_demo_data

Requires:
    - BACKEND_DIR/.env with SUPABASE_URL and SUPABASE_SERVICE_KEY
    - The database is migrated (remote_checkins table and work_mode column exist)
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import sys
import uuid
from datetime import datetime, timedelta, timezone

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("seed_remote_demo")

DEMO_PREFIX = "DEMO_"
NORMAL_COUNT = 10
ANOMALOUS_COUNT = 2
TOTAL_WORKERS = NORMAL_COUNT + ANOMALOUS_COUNT

NORMAL_CHECKINS_MIN = 5
NORMAL_CHECKINS_MAX = 7
CHECKIN_HOUR_MIN = 8
CHECKIN_HOUR_MAX = 9
CHECKIN_JITTER_MINUTES = 15

LAGOS = {"lat": 6.5244, "lng": 3.3792}
ABUJA = {"lat": 9.0765, "lng": 7.3986}
IBADAN = {"lat": 7.3775, "lng": 3.9470}
PORT_HARCOURT = {"lat": 4.8156, "lng": 7.0498}
BENIN = {"lat": 6.3176, "lng": 5.6145}
ENUGU = {"lat": 6.4488, "lng": 7.5114}
KANO = {"lat": 11.9980, "lng": 8.5357}
JOS = {"lat": 9.8905, "lng": 8.8581}
WARRI = {"lat": 5.5173, "lng": 5.7506}
CALABAR = {"lat": 4.9757, "lng": 8.3415}

CITIES = [
    {"name": "Lagos", "lat": LAGOS["lat"], "lng": LAGOS["lng"]},
    {"name": "Ibadan", "lat": IBADAN["lat"], "lng": IBADAN["lng"]},
    {"name": "Port Harcourt", "lat": PORT_HARCOURT["lat"], "lng": PORT_HARCOURT["lng"]},
    {"name": "Benin", "lat": BENIN["lat"], "lng": BENIN["lng"]},
    {"name": "Enugu", "lat": ENUGU["lat"], "lng": ENUGU["lng"]},
    {"name": "Kano", "lat": KANO["lat"], "lng": KANO["lng"]},
    {"name": "Jos", "lat": JOS["lat"], "lng": JOS["lng"]},
    {"name": "Warri", "lat": WARRI["lat"], "lng": WARRI["lng"]},
    {"name": "Calabar", "lat": CALABAR["lat"], "lng": CALABAR["lng"]},
    {"name": "Abuja", "lat": ABUJA["lat"], "lng": ABUJA["lng"]},
]

FIRST_NAMES = [
    "Amina", "Chidi", "Folake", "Emeka", "Zainab",
    "Kelechi", "Simi", "Tunde", "Yewande", "Kunle",
    "Nneka", "Babajide",
]
LAST_NAMES = [
    "Okafor", "Adebayo", "Nwosu", "Balogun", "Eze",
    "Ogunleye", "Okoro", "Usman", "Abubakar", "Olatunji",
    "Okonkwo", "Sowemimo",
]

BANKS = [
    {"name": "Access Bank", "code": "044"},
    {"name": "GTBank", "code": "058"},
    {"name": "First Bank", "code": "011"},
    {"name": "Zenith Bank", "code": "057"},
    {"name": "UBA", "code": "033"},
    {"name": "Providus Bank", "code": "101"},
]


def _connect():
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from app.database import get_supabase
    return get_supabase()


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _random_lat(base: float, jitter: float = 0.02) -> float:
    return round(base + random.uniform(-jitter, jitter), 6)


def _random_lng(base: float, jitter: float = 0.02) -> float:
    return round(base + random.uniform(-jitter, jitter), 6)


def _generate_ip(index: int) -> str:
    return f"10.{random.randint(1, 254)}.{random.randint(1, 254)}.{index + 10}"


def _generate_phone(index: int) -> str:
    return f"+234800{index:03d}0{index:02d}"


def _generate_email(index: int) -> str:
    return f"{DEMO_PREFIX.lower()}remote.worker{index}@example.com"


def _generate_account_number(index: int) -> str:
    return f"0{index:09d}"


def _fingerprint(worker_num: int) -> str:
    seed = f"demo-device-fp-{worker_num}"
    import hashlib
    return hashlib.sha256(seed.encode()).hexdigest()


def _check_demo_exists(db) -> bool:
    result = (
        db.table("workers")
        .select("id")
        .eq("email", _generate_email(0))
        .limit(1)
        .execute()
    )
    if result.data:
        logger.warning(
            "Demo worker with email '%s' already exists — skipping. "
            "Delete demo workers first if you want to re-seed.",
            _generate_email(0),
        )
        return True
    return False


def _find_company(db, auto_yes: bool = False) -> str:
    result = db.table("companies").select("id, name").limit(1).execute().data
    if not result:
        logger.error("No companies found in the database. Create a company first.")
        sys.exit(1)
    company = result[0]
    print(f"\nUsing company: {company['name']} ({company['id']})")
    if not auto_yes:
        answer = input("Is this correct? (yes/no): ").strip().lower()
        if answer == "no":
            logger.error("Cannot proceed without a valid company_id.")
            sys.exit(1)
    return company["id"]


def _find_or_create_role(db, company_id: str) -> str:
    result = (
        db.table("roles")
        .select("id")
        .eq("company_id", company_id)
        .eq("role_name", "Remote Staff")
        .limit(1)
        .execute()
        .data
    )
    if result:
        return result[0]["id"]

    logger.info("Creating 'Remote Staff' role with a dummy invite code …")
    import hashlib
    code = "REMOTE_DEMO_" + hashlib.md5(str(_now()).encode()).hexdigest()[:8].upper()
    insert = (
        db.table("roles")
        .insert({
            "company_id": company_id,
            "role_name": "Remote Staff",
            "department": "Remote Operations",
            "grade_level": "Mid",
            "headcount_max": 50,
            "headcount_filled": 0,
            "gross_salary": 250000.00,
            "pension_deduct": 22500.00,
            "health_deduct": 5000.00,
            "other_deductions": 2000.00,
            "work_type": "REMOTE",
            "invite_code": code,
            "code_active": False,
        })
        .execute()
        .data
    )
    if not insert:
        logger.error("Failed to create 'Remote Staff' role.")
        sys.exit(1)
    role = insert[0] if isinstance(insert, list) else insert
    return role["id"]


def _create_workers(db, company_id: str, role_id: str) -> list[dict]:
    workers = []
    for i in range(TOTAL_WORKERS):
        first = FIRST_NAMES[i]
        last = LAST_NAMES[i]
        worker_id = str(uuid.uuid4())
        email = _generate_email(i)
        phone = _generate_phone(i)

        insert = (
            db.table("workers")
            .insert({
                "id": worker_id,
                "company_id": company_id,
                "role_id": role_id,
                "first_name": f"{DEMO_PREFIX}{first}",
                "last_name": last,
                "email": email,
                "phone_number": phone,
                "gender": random.choice(["Male", "Female"]),
                "date_of_birth": f"19{random.randint(70, 99)}-{random.randint(1, 12):02d}-{random.randint(1, 28):02d}",
                "home_address": f"{random.randint(1, 100)} Demo Street",
                "state_of_origin": random.choice(["Lagos", "Oyo", "Rivers", "Enugu", "Kano", "FCT"]),
                "next_of_kin_name": "Next of Kin",
                "next_of_kin_phone": _generate_phone(i + 100),
                "emergency_contact_name": "Emergency Contact",
                "emergency_contact_phone": _generate_phone(i + 200),
                "nin": f"{i:011d}",
                "bank_verified": True,
                "status": "ACTIVE",
                "work_mode": "remote",
                "completeness_score": round(random.uniform(0.5, 0.95), 2),
            })
            .execute()
            .data
        )
        if not insert:
            logger.error("Failed to create worker %d (%s %s). Aborting.", i, first, last)
            sys.exit(1)
        record = insert[0] if isinstance(insert, list) else insert

        bank = random.choice(BANKS)
        db.table("worker_bank_accounts").insert({
            "worker_id": worker_id,
            "bank_name": bank["name"],
            "bank_code": bank["code"],
            "account_number": _generate_account_number(i),
            "account_name": f"{first} {last}",
            "is_active": True,
        }).execute()

        workers.append({
            "id": worker_id,
            "num": i,
            "first_name": first,
            "last_name": last,
            "is_anomalous": i >= NORMAL_COUNT,
        })
        logger.info("Created worker %d/%d: %s %s (id=%s)", i + 1, TOTAL_WORKERS, first, last, worker_id[:8])

    return workers


def _create_normal_checkins(db, workers: list[dict]) -> dict[int, str]:
    device_fingerprint_map: dict[int, str] = {}
    now = _now()

    for w in workers:
        if w["is_anomalous"]:
            continue

        num = w["num"]
        city = CITIES[num % len(CITIES)]
        fp = _fingerprint(num)
        device_fingerprint_map[num] = fp
        ip = _generate_ip(num)

        num_checkins = random.randint(NORMAL_CHECKINS_MIN, NORMAL_CHECKINS_MAX)

        for ci in range(num_checkins):
            days_ago = random.randint(0, 13)
            base_hour = random.uniform(CHECKIN_HOUR_MIN, CHECKIN_HOUR_MAX)
            minute_jitter = random.uniform(-CHECKIN_JITTER_MINUTES, CHECKIN_JITTER_MINUTES) / 60.0
            hour = base_hour + minute_jitter
            hour = max(6.0, min(20.0, hour))

            ts = now - timedelta(days=days_ago)
            ts = ts.replace(hour=int(hour), minute=int((hour % 1) * 60), second=random.randint(0, 59))

            db.table("remote_checkins").insert({
                "worker_id": w["id"],
                "checked_in_at": ts.isoformat(),
                "ip_address": ip,
                "device_fingerprint": fp,
                "geo_lat": _random_lat(city["lat"]),
                "geo_lng": _random_lng(city["lng"]),
                "geo_city": city["name"],
                "geo_country": "Nigeria",
            }).execute()

        logger.info("  %s %s: %d check-ins @ %s", w["first_name"], w["last_name"], num_checkins, city["name"])

    return device_fingerprint_map


def _create_anomalous_worker_a(db, worker: dict, normal_fp_map: dict[int, str]) -> None:
    """Device-fingerprint reuse: this worker uses a normal worker's fingerprint."""
    target_normal_num = random.choice(list(normal_fp_map.keys()))
    stolen_fp = normal_fp_map[target_normal_num]
    num = worker["num"]
    city = CITIES[num % len(CITIES)]
    ip = _generate_ip(num + 100)

    num_checkins = random.randint(NORMAL_CHECKINS_MIN, NORMAL_CHECKINS_MAX)
    now = _now()

    for ci in range(num_checkins):
        days_ago = random.randint(0, 13)
        base_hour = random.uniform(CHECKIN_HOUR_MIN, CHECKIN_HOUR_MAX)
        minute_jitter = random.uniform(-CHECKIN_JITTER_MINUTES, CHECKIN_JITTER_MINUTES) / 60.0
        hour = base_hour + minute_jitter
        hour = max(6.0, min(20.0, hour))

        ts = now - timedelta(days=days_ago)
        ts = ts.replace(hour=int(hour), minute=int((hour % 1) * 60), second=random.randint(0, 59))

        db.table("remote_checkins").insert({
            "worker_id": worker["id"],
            "checked_in_at": ts.isoformat(),
            "ip_address": ip,
            "device_fingerprint": stolen_fp,
            "geo_lat": _random_lat(city["lat"]),
            "geo_lng": _random_lng(city["lng"]),
            "geo_city": city["name"],
            "geo_country": "Nigeria",
        }).execute()

    logger.info(
        "  %s %s (ANOMALOUS): %d check-ins, device FP reused from worker %d (%s)",
        worker["first_name"], worker["last_name"], num_checkins,
        target_normal_num, FIRST_NAMES[target_normal_num],
    )


def _create_anomalous_worker_b(db, worker: dict) -> None:
    """Impossible travel: two check-ins close in time but far apart geographically."""
    num = worker["num"]
    ip = _generate_ip(num + 200)
    fp = _fingerprint(900 + num)
    now = _now()

    normal_count = random.randint(3, 4)
    for ci in range(normal_count):
        days_ago = random.randint(0, 13)
        ts = now - timedelta(days=days_ago)
        ts = ts.replace(hour=9, minute=random.randint(0, 30), second=random.randint(0, 59))
        db.table("remote_checkins").insert({
            "worker_id": worker["id"],
            "checked_in_at": ts.isoformat(),
            "ip_address": ip,
            "device_fingerprint": fp,
            "geo_lat": _random_lat(LAGOS["lat"]),
            "geo_lng": _random_lng(LAGOS["lng"]),
            "geo_city": "Lagos",
            "geo_country": "Nigeria",
        }).execute()

    recent_day = now - timedelta(days=random.randint(0, 2))
    ts1 = recent_day.replace(hour=8, minute=0, second=0)
    ts2 = ts1 + timedelta(minutes=20)

    db.table("remote_checkins").insert({
        "worker_id": worker["id"],
        "checked_in_at": ts1.isoformat(),
        "ip_address": ip,
        "device_fingerprint": fp,
        "geo_lat": _random_lat(LAGOS["lat"]),
        "geo_lng": _random_lng(LAGOS["lng"]),
        "geo_city": "Lagos",
        "geo_country": "Nigeria",
    }).execute()

    db.table("remote_checkins").insert({
        "worker_id": worker["id"],
        "checked_in_at": ts2.isoformat(),
        "ip_address": ip,
        "device_fingerprint": fp,
        "geo_lat": _random_lat(ABUJA["lat"]),
        "geo_lng": _random_lng(ABUJA["lng"]),
        "geo_city": "Abuja",
        "geo_country": "Nigeria",
    }).execute()

    logger.info(
        "  %s %s (ANOMALOUS): %d normal check-ins + impossible-travel pair "
        "(Lagos → Abuja in 20 min)",
        worker["first_name"], worker["last_name"], normal_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed remote demo workers")
    parser.add_argument("--yes", "-y", action="store_true", help="Auto-confirm company selection")
    args = parser.parse_args()

    print("=" * 72)
    print("  SEED REMOTE DEMO DATA")
    print("=" * 72)

    db = _connect()

    if _check_demo_exists(db):
        sys.exit(0)

    company_id = _find_company(db, auto_yes=args.yes)
    role_id = _find_or_create_role(db, company_id)

    print(f"\nCreating {TOTAL_WORKERS} remote demo workers …")
    workers = _create_workers(db, company_id, role_id)
    normal_workers = [w for w in workers if not w["is_anomalous"]]
    anomalous_workers = [w for w in workers if w["is_anomalous"]]

    print(f"\nGenerating normal check-in history for {NORMAL_COUNT} workers …")
    normal_fp_map = _create_normal_checkins(db, normal_workers)

    print(f"\nGenerating anomalous check-in history for {ANOMALOUS_COUNT} workers …")
    _create_anomalous_worker_a(db, anomalous_workers[0], normal_fp_map)
    _create_anomalous_worker_b(db, anomalous_workers[1])

    checkin_counts = (
        db.table("remote_checkins")
        .select("worker_id, checked_in_at")
        .execute()
        .data
    )
    per_worker: dict[str, int] = {}
    for row in checkin_counts:
        per_worker.setdefault(row["worker_id"], 0)
        per_worker[row["worker_id"]] += 1

    print("\n" + "=" * 72)
    print("  SEED SUMMARY")
    print("=" * 72)
    print(f"  Total workers created:  {TOTAL_WORKERS}")
    print(f"  Normal workers:         {NORMAL_COUNT}")
    print(f"  Anomalous workers:      {ANOMALOUS_COUNT}")
    print()

    for w in workers:
        c = per_worker.get(w["id"], 0)
        tag = ""
        if w["is_anomalous"]:
            tag = " <<< ANOMALOUS"
        print(f"  {w['first_name']:12s} {w['last_name']:12s}  {c} check-ins{tag}")

    print()
    print("  Anomalous workers (for demo reference):")
    print(
        f"    Worker A -- '{anomalous_workers[0]['first_name']} "
        f"{anomalous_workers[0]['last_name']}': "
        f"device_fingerprint reuse -> triggers 'device_fingerprint_reuse' flag"
    )
    print(
        f"    Worker B -- '{anomalous_workers[1]['first_name']} "
        f"{anomalous_workers[1]['last_name']}': "
        f"impossible travel (Lagos->Abuja in 20 min) -> triggers 'impossible_travel' flag"
    )
    print()
    print("  Done. To verify, run:")
    print("    GET /admin/payroll/risk-summary")
    print("=" * 72)


if __name__ == "__main__":
    main()
