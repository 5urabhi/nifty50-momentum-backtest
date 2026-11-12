"""Read-only Dhan credential and market-data entitlement diagnostics.

Uses Dhan's published GET /v2/profile. Never sends account identifiers,
tokens, names, or raw vendor response bodies to the React interface.
"""
from __future__ import annotations
import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def check_profile(opener=urlopen) -> dict:
    token = os.getenv("DHAN_ACCESS_TOKEN", "").strip()
    if not token:
        return {"ok": False, "token_present": False, "token_valid": False,
                "data_plan_active": False, "code": "token_missing",
                "message": "Set DHAN_ACCESS_TOKEN in the project .env and restart QuantLab."}
    req = Request("https://api.dhan.co/v2/profile", headers={
        "access-token": token, "Accept": "application/json",
    }, method="GET")
    try:
        with opener(req, timeout=12) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as exc:
        if exc.code in (401, 403):
            return {"ok": False, "token_present": True, "token_valid": False,
                    "data_plan_active": False, "code": "auth_rejected",
                    "message": "Dhan rejected this access token. Generate a fresh token in Dhan Web; restart the workstation."}
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "profile_http_error",
                "message": f"Dhan profile endpoint returned HTTP {exc.code}; token status not verified."}
    except (URLError, TimeoutError, OSError, ValueError, TypeError):
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "profile_unreachable",
                "message": "Could not verify Dhan API credentials; check connectivity and retry."}
    if not isinstance(payload, dict):
        return {"ok": False, "token_present": True, "token_valid": None,
                "data_plan_active": None, "code": "invalid_profile",
                "message": "Dhan returned an unrecognized profile response."}
    # Dhan V2 documents tokenValidity, dataPlan and dataValidity.
    # Never emit dhanClientId, UCC, account details or token content.
    state = str(payload.get("dataPlan", "")).strip().lower()
    token_valid = bool(payload.get("tokenValidity"))
    plan_active = state == "active"
    if not token_valid:
        code, message = "token_unverified", "Dhan did not confirm token validity. Refresh the token and retry."
    elif not plan_active:
        code, message = "data_plan_inactive", "Dhan Data API subscription is not active. Trading API access alone does not enable historical market-data requests."
    else:
        code, message = "ready", "Dhan authenticated and reports an active Data API subscription."
    return {"ok": bool(token_valid and plan_active), "token_present": True,
            "token_valid": token_valid, "data_plan_active": plan_active,
            "code": code, "message": message,
            "token_validity": str(payload.get("tokenValidity", ""))[:40],
            "data_validity": str(payload.get("dataValidity", ""))[:40]}
