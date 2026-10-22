"""A stand-in REST API for the MCP tests: canned answers, and it records who called."""

from typing import Any

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

TOKENS = {
    "tok-planner": {"role": "planner", "display_name": "Dr. Thomas Brandt"},
    "tok-oversight": {"role": "oversight", "display_name": "Katrin Vogel"},
    "tok-staff": {"role": "staff", "display_name": "Dr. Aylin Kaya"},
}
CALLS: list[tuple[str, str, str | None]] = []  # (method, path, authorization)
SID = "0fa0e226-bbae-5a54-b05a-db82a17ca3d0"
SID2 = "1fa0e226-bbae-5a54-b05a-db82a17ca3d0"


def _user(request: Request) -> dict[str, Any] | None:
    auth = request.headers.get("authorization", "")
    return TOKENS.get(auth.removeprefix("Bearer ")) if auth.startswith("Bearer ") else None


async def me(request: Request) -> JSONResponse:
    """GET /me."""
    CALLS.append(("GET", "/me", request.headers.get("authorization")))
    u = _user(request)
    if u is None:
        return JSONResponse({"detail": "bad token"}, status_code=401)
    return JSONResponse(
        {"id": "u", "persona_key": "p", "department_id": "d", "staff_id": None, **u}
    )


def _record(request: Request) -> None:
    CALLS.append((request.method, request.url.path, request.headers.get("authorization")))


async def roster(request: Request) -> JSONResponse:
    """GET /roster (with names and an absence category, which the tools must not pass on)."""
    _record(request)
    return JSONResponse(
        {
            "roster_month": "2026-11-01",
            "status": "published",
            "published_at": None,
            "rule_set_version": "2026-1",
            "rows": [
                {
                    "staff_id": SID,
                    "display_name": "Dr. Jonas Weber",
                    "title_de": "Assistenzarzt",
                    "title_en": "Resident",
                    "cells": {
                        "2026-11-03": {
                            "shifts": ["frueh"],
                            "assignment_ids": ["a1"],
                            "changed": False,
                            "on_leave": False,
                            "absence": {"status": "absent", "category": "sick"},
                        }
                    },
                }
            ],
            "coverage": [
                {
                    "date": "2026-11-03",
                    "shift_type": "frueh",
                    "qualification": "any",
                    "required": 2,
                    "assigned": 1,
                }
            ],
            "gaps": [],
        }
    )


async def fairness(request: Request) -> JSONResponse:
    """GET /fairness."""
    _record(request)
    people = (
        [
            {
                "staff_id": SID,
                "display_name": "Dr. Jonas Weber",
                "nights": 3,
                "weekends": 2,
                "holidays": 1,
            }
        ]
        if _user(request) and _user(request)["role"] == "planner"
        else None
    )
    return JSONResponse(
        {
            "year": 2026,
            "as_of": "2026-10-20",
            "distributions": [
                {
                    "metric": "nights",
                    "people": 20,
                    "mean": 3.0,
                    "median": 3.0,
                    "minimum": 1,
                    "maximum": 5,
                    "values": [1, 5],
                }
            ],
            "people": people,
        }
    )


async def what_if(request: Request) -> JSONResponse:
    """POST /planner/what-if."""
    _record(request)
    return JSONResponse(
        {
            "valid": False,
            "introduced": [
                {
                    "rule": "min_rest",
                    "key": "k",
                    "staff_id": SID,
                    "display_name": "Dr. Jonas Weber",
                    "date": "2026-11-03",
                    "params": {"hours": 8},
                    "fix_key": "f",
                    "fix_params": {},
                }
            ],
            "people": [{"staff_id": SID, "hours_delta": 8.0}],
            "removed_without_replacement": [],
            "validator": {"component": "C2", "version": "v1"},
        }
    )


async def proposals(request: Request) -> JSONResponse:
    """POST /copilot/proposals."""
    _record(request)
    if _user(request)["role"] != "planner":  # type: ignore[index]
        return JSONResponse({"detail": "Not allowed for role"}, status_code=403)
    return JSONResponse({"id": "p1", "status": "open"}, status_code=201)


async def rules(request: Request) -> JSONResponse:
    """GET /rules/search."""
    _record(request)
    return JSONResponse(
        {
            "query": "q",
            "found": True,
            "passages": [
                {
                    "id": "arbzg:§5:1",
                    "citation": "ArbZG § 5 Abs. 1 (Stand 2024-12-31)",
                    "section": "§ 5",
                    "paragraph": 1,
                    "heading": "Ruhezeit",
                    "text": "elf Stunden",
                    "language": "de",
                    "synthetic": False,
                    "score": 0.03,
                    "cosine": 0.7,
                }
            ],
            "mode": "fts-only" if request.query_params.get("q") == "nomodel" else "vector",
            "configured": "vector",
            "fallback": request.query_params.get("q") == "nomodel",
            "vector_used": request.query_params.get("q") != "nomodel",
        }
    )


async def forbidden(request: Request) -> JSONResponse:
    """A route that always answers 403, to see how errors reach the model."""
    _record(request)
    return JSONResponse({"detail": "Not allowed for role oversight"}, status_code=403)


def make() -> Starlette:
    """Return the fake API."""
    return Starlette(
        routes=[
            Route("/me", me),
            Route("/roster", roster),
            Route("/fairness", fairness),
            Route("/planner/what-if", what_if, methods=["POST"]),
            Route("/copilot/proposals", proposals, methods=["POST"]),
            Route("/rules/search", rules),
            Route("/planner/runs", forbidden),
        ]
    )
