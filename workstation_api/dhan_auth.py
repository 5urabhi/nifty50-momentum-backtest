"""Read-only Dhan credential and market-data entitlement diagnostics.

Uses Dhan's published GET /v2/profile. Never sends account identifiers,
tokens, names, or raw vendor response bodies to the React interface.
"""
from __future__ import annotations
import json
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

LOG = logging.getLogger("quantlab.dhan.auth")


def check_profile(opener=urlopen) -> dict:
    token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    if not token:
        LOG.warning("Dhan profile preflight: token is missing from environment")
        return {"ok": False, "token_present": False, "token_valid": False,
                "data_plan_active": False, "code": "token_missing",
                "message": "Set DHAN_ACCESS_TOKEN in the project .env and restart QuantLab."}
    req = Request("https://api.dhan.co/v2/profile", headers={
        "access-token": token, "Accept": "application/json",
    }, method="GET")
    LOG.info("Dhan profile preflight started: endpoint=GET /v2/profile token_present=yes")
    try:
        with opener(req, timeout=12) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as exc:
        LOG.warning("Dhan profile preflight HTTP failure: endpoint=GET /v2/profile status=%s", exc.code)
        if exc.code in (401, 403):
            return {"ok": False, "token_present": True, "token_valid": False,
                    "data_plan_active": False, "code": "auth_rejected",
                    "message": "Dhan rejected this access token. Generate a fresh token in Dhan Web; restart the workstation."}
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "profile_http_error",
                "message": f"Dhan profile endpoint returned HTTP {exc.code}; token status not verified."}
    except (URLError, TimeoutError, OSError, ValueError, TypeError) as exc:
        LOG.warning("Dhan profile preflight failed: endpoint=GET /v2/profile category=%s", type(exc).__name__)
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "profile_unreachable",
                "message": "Could not verify Dhan API credentials; check connectivity and retry."}
    if not isinstance(payload, dict):
        LOG.warning("Dhan profile preflight unexpected response type")
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "invalid_profile",
                "message": "Dhan returned an unrecognized profile response."}
    # Dhan V2 documents tokenValidity, dataPlan and dataValidity.
    # Never emit dhanClientId, UCC, account details or token content.
    state = str(payload.get("dataPlan", "")).strip().lower()
    # Dhan documents tokenValidity as DD/MM/YYYY HH:MM (an expiry timestamp),
    # NOT a boolean. Nonempty strings are not evidence of an active token.
    expiry = str(payload.get("tokenValidity", "")).strip()
    try:
        valid_until = datetime.strptime(expiry, "%d/%m/%Y %H:%M").replace(
            tzinfo=ZoneInfo("Asia/Kolkata"))
        token_valid = datetime.now(ZoneInfo("Asia/Kolkata")) < valid_until
    except ValueError:
        token_valid = None
    plan_active = state == "active"
    if token_valid is False:
        code, message = "token_expired", "Dhan access token expired. Generate a fresh access token in Dhan Web and restart the workstation."
    elif token_valid is None:
        code, message = "token_expiry_unknown", "Dhan authenticated, but the token expiry field could not be interpreted."
    elif not plan_active:
        code, message = "data_plan_inactive", "Dhan Data API subscription is not active. Trading API access alone does not enable historical market-data requests."
    else:
        code, message = "ready", "Dhan authenticated and reports an active Data API subscription."
    LOG.log(logging.INFO if code == "ready" else logging.WARNING,
            "Dhan profile preflight result: code=%s token_valid=%s data_plan_active=%s",
            code, token_valid, plan_active)
    return {"ok": bool(token_valid and plan_active), "token_present": True,
            "token_valid": token_valid, "data_plan_active": plan_active,
            "code": code, "message": message,
            "token_validity": expiry[:40],
            "data_validity": str(payload.get("dataValidity", ""))[:40]}
