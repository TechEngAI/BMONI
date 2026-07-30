import logging
from typing import Any

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

from app.database import get_supabase
from app.ml.engine import run_ghost_detection
from app.ml.features import compute_company_features, extract_remote_features

logger = logging.getLogger(__name__)

REMOTE_FEATURE_COLUMNS = [
    "checkin_time_std_dev",
    "device_fingerprint_reuse_count",
    "ip_reuse_across_workers",
    "impossible_travel_flag",
]

# Adjustable threshold: for a hackathon demo with a small worker count,
# this may need to be lowered.  Check your demo dataset size against it.
REMOTE_BATCH_MIN_WORKERS = 10

RISK_SCORE_HOLD_THRESHOLD = 70


async def score_remote_workers_batch(company_id: str) -> dict[str, dict[str, Any]]:
    db = get_supabase()
    workers = (
        db.table("workers")
        .select("id")
        .eq("company_id", company_id)
        .eq("status", "ACTIVE")
        .eq("work_mode", "remote")
        .execute()
        .data
    )

    if len(workers) < REMOTE_BATCH_MIN_WORKERS:
        logger.info(
            "Insufficient remote workers (%d) for batch Isolation Forest. "
            "Need at least %d. Remote risk scores will use rule-only fallback.",
            len(workers), REMOTE_BATCH_MIN_WORKERS,
        )
        result: dict[str, dict[str, Any]] = {}
        for w in workers:
            features = await extract_remote_features(w["id"])
            flags = _remote_rule_flags(features)
            result[w["id"]] = {
                "ml_score": 50.0,
                "flags": flags,
                "scoring_method": "fallback",
                "feature_values": features,
            }
        return result

    feature_rows = []
    for w in workers:
        features = await extract_remote_features(w["id"])
        feature_rows.append(features)

    df = pd.DataFrame(feature_rows)
    x = df[REMOTE_FEATURE_COLUMNS].fillna(0.0)
    scaler = StandardScaler()
    x_scaled = scaler.fit_transform(x)
    model = IsolationForest(
        contamination=0.10,
        n_estimators=200,
        random_state=42,
        max_samples="auto",
    )
    model.fit_predict(x_scaled)
    raw_scores = model.score_samples(x_scaled)

    min_score = raw_scores.min()
    max_score = raw_scores.max()
    if min_score == max_score:
        norm_scores = np.full(len(raw_scores), 50.0)
    else:
        norm_scores = ((raw_scores - min_score) / (max_score - min_score)) * 100

    result = {}
    for i, row in df.iterrows():
        wid = row["worker_id"]
        ml_score = round(float(norm_scores[i]), 2)
        features = feature_rows[i]
        flags = _remote_rule_flags(features)
        result[wid] = {
            "ml_score": ml_score,
            "flags": flags,
            "scoring_method": "batch",
            "feature_values": features,
        }

    return result


def _remote_rule_flags(features: dict[str, Any]) -> list[str]:
    flags: list[str] = []
    if features.get("device_fingerprint_reuse_count", 0) > 0:
        flags.append("device_fingerprint_reuse")
    if features.get("ip_reuse_across_workers", 0) > 0:
        flags.append("ip_reuse_across_workers")
    if features.get("impossible_travel_flag", False):
        flags.append("impossible_travel")
    return flags


async def score_physical_workers_batch(
    company_id: str, month_year: str
) -> dict[str, dict[str, Any]]:
    db = get_supabase()
    workers = (
        db.table("workers")
        .select("id")
        .eq("company_id", company_id)
        .eq("status", "ACTIVE")
        .eq("work_mode", "physical")
        .execute()
        .data
    )

    if not workers:
        return {}

    feature_rows = await compute_company_features(company_id, month_year)

    if not feature_rows:
        return {}

    physical_feature_rows = [r for r in feature_rows if r["worker_id"] in {w["id"] for w in workers}]

    if not physical_feature_rows:
        return {}

    engine_results = run_ghost_detection(physical_feature_rows)
    result: dict[str, dict[str, Any]] = {}
    for r in engine_results:
        wid = r["worker_id"]
        result[wid] = {
            "ml_score": r["trust_score"],
            "flags": [],
            "scoring_method": "batch",
            "feature_values": r["feature_values"],
        }

    return result


async def detect_bank_account_reuse(
    company_id: str, worker_id: str
) -> bool:
    db = get_supabase()
    worker_account = (
        db.table("worker_bank_accounts")
        .select("account_number")
        .eq("worker_id", worker_id)
        .eq("is_active", True)
        .maybe_single()
        .execute()
        .data
    )
    if not worker_account:
        return False

    dupes = (
        db.table("worker_bank_accounts")
        .select("worker_id")
        .eq("account_number", worker_account["account_number"])
        .eq("is_active", True)
        .neq("worker_id", worker_id)
        .limit(1)
        .execute()
        .data
    )
    return len(dupes) > 0


async def compute_risk_score(
    worker_id: str,
    *,
    batch_scores: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    db = get_supabase()
    worker = (
        db.table("workers")
        .select("id, company_id, work_mode")
        .eq("id", worker_id)
        .maybe_single()
        .execute()
        .data
    )
    if not worker:
        return {
            "worker_id": worker_id,
            "risk_score": 50,
            "flags": ["worker_not_found"],
            "work_mode": "unknown",
            "scoring_method": "fallback",
        }

    company_id = worker["company_id"]
    work_mode = worker.get("work_mode", "physical")

    if batch_scores and worker_id in batch_scores:
        entry = batch_scores[worker_id]
        ml_score = entry["ml_score"]
        flags = list(entry["flags"])
        scoring_method = "batch"
    else:
        logger.warning(
            "Degenerate fallback scoring path for worker %s — no batch_scores provided. "
            "This path exists for ad-hoc single-worker queries only; it MUST NOT be used "
            "in the main payroll batch flow because a single vector cannot be meaningfully "
            "scored by an Isolation Forest.",
            worker_id,
        )
        ml_score = 50.0
        flags = []
        scoring_method = "fallback"
        if work_mode == "remote":
            features = await extract_remote_features(worker_id)
            flags = _remote_rule_flags(features)

    bank_reuse = await detect_bank_account_reuse(company_id, worker_id)
    if bank_reuse:
        flags.append("bank_account_reuse")

    flag_penalty = min(len(flags) * 25, 100)
    raw_score = ml_score + flag_penalty
    risk_score = min(int(round(raw_score)), 100)

    return {
        "worker_id": worker_id,
        "risk_score": risk_score,
        "flags": flags,
        "work_mode": work_mode,
        "scoring_method": scoring_method,
    }
