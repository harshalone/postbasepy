"""Internal helpers shared by the sync and async clients.

Not part of the public API — names here may change without notice.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Any, Dict, List, Tuple

from .types import Filter


def base64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_code_verifier() -> str:
    return base64url_encode(os.urandom(32))


def generate_code_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64url_encode(digest)


def generate_state() -> str:
    return base64url_encode(os.urandom(16))


def random_verifier_pair() -> Tuple[str, str, str]:
    """Returns (code_verifier, code_challenge, state) for a PKCE OAuth flow."""
    verifier = generate_code_verifier()
    challenge = generate_code_challenge(verifier)
    state = generate_state()
    return verifier, challenge, state


def secure_token() -> str:
    return secrets.token_urlsafe(24)


# ─── Column parsing (SELECT "col AS alias" support) ────────────────────────


class ParsedColumn:
    __slots__ = ("col", "alias")

    def __init__(self, col: str, alias: str) -> None:
        self.col = col
        self.alias = alias


def parse_columns(columns: str) -> List[ParsedColumn]:
    parsed: List[ParsedColumn] = []
    for raw in columns.split(","):
        part = raw.strip()
        lower = part.lower()
        as_idx = -1
        i = 0
        while True:
            idx = lower.find(" as ", i)
            if idx == -1:
                break
            as_idx = idx
            i = idx + 1
        if as_idx == -1:
            parsed.append(ParsedColumn(part, part))
            continue
        col = part[:as_idx].strip()
        alias = part[as_idx + 4 :].strip()
        parsed.append(ParsedColumn(col, alias))
    return parsed


def apply_aliases(rows: List[Dict[str, Any]], parsed: List[ParsedColumn]) -> List[Dict[str, Any]]:
    alias_map: Dict[str, str] = {}
    for p in parsed:
        if p.col != p.alias:
            server_key = p.col.split(".")[-1] if "." in p.col else p.col
            alias_map.setdefault(server_key, p.alias)
    if not alias_map:
        return rows
    out: List[Dict[str, Any]] = []
    for row in rows:
        new_row: Dict[str, Any] = {}
        for k, v in row.items():
            new_row[alias_map.get(k, k)] = v
        out.append(new_row)
    return out


# ─── OR filter string parser ────────────────────────────────────────────────
#
# Parses Supabase/postbasejs-style filter strings into structured Filter lists.
#   "email.ilike.%foo%,name.ilike.%foo%"  -> [Filter, Filter]
#   "status.eq.active,age.gt.18"          -> [Filter, Filter]
#   "role.in.(admin,owner)"               -> [Filter(op="in", value=[...])]
#
# The value is everything after the second dot, so dots in values are safe.
# Commas inside balanced parentheses (for the `in` operator) are not split on.


def parse_or_filter_string(filter_str: str) -> List[Filter]:
    segments: List[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(filter_str):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            segments.append(filter_str[start:i].strip())
            start = i + 1
    segments.append(filter_str[start:].strip())

    filters: List[Filter] = []
    for seg in segments:
        if not seg:
            continue
        first_dot = seg.find(".")
        second_dot = seg.find(".", first_dot + 1)
        if first_dot == -1 or second_dot == -1:
            filters.append(Filter(column=seg, operator="eq", value=None))
            continue
        column = seg[:first_dot]
        operator = seg[first_dot + 1 : second_dot]
        raw_value = seg[second_dot + 1 :]

        value: Any = raw_value
        if operator == "in":
            inner = raw_value
            if inner.startswith("("):
                inner = inner[1:]
            if inner.endswith(")"):
                inner = inner[:-1]
            value = [v.strip() for v in inner.split(",")]
        elif raw_value == "true":
            value = True
        elif raw_value == "false":
            value = False
        elif raw_value == "null":
            value = None

        filters.append(Filter(column=column, operator=operator, value=value))  # type: ignore[arg-type]
    return filters


def filter_to_dict(f: Filter) -> Dict[str, Any]:
    return {"column": f.column, "operator": f.operator, "value": f.value}


def filters_to_dicts(filters: List[Filter]) -> List[Dict[str, Any]]:
    return [filter_to_dict(f) for f in filters]
