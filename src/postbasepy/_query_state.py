"""Query state shared by sync and async query builders."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Literal, Optional, Union

from .types import Filter, JoinClause, OrderBy

Operation = Literal["select", "insert", "update", "delete", "upsert"]


@dataclass(frozen=True)
class QueryState:
    base_url: str
    api_key: str
    table: str
    columns: str = "*"
    select_count: Optional[str] = None
    select_head: Optional[bool] = None
    filters: List[Filter] = field(default_factory=list)
    or_filters: List[List[Filter]] = field(default_factory=list)
    not_filters: List[Dict[str, Any]] = field(default_factory=list)
    order_by: List[OrderBy] = field(default_factory=list)
    joins: List[JoinClause] = field(default_factory=list)
    limit_: Optional[int] = None
    offset_: Optional[int] = None
    range_: Optional[Dict[str, int]] = None
    operation: Operation = "select"
    insert_data: Optional[Union[Dict[str, Any], List[Dict[str, Any]]]] = None
    upsert_on_conflict: Optional[str] = None
    update_data: Optional[Dict[str, Any]] = None
    returning: Optional[str] = None
    extra_headers: Dict[str, str] = field(default_factory=dict)
    session_token: Optional[str] = None

    def evolve(self, **changes: Any) -> QueryState:
        return replace(self, **changes)


def build_request_body(state: QueryState) -> Dict[str, Any]:
    body: Dict[str, Any] = {
        "operation": "upsert" if state.operation == "upsert" else state.operation,
        "table": state.table,
    }

    parsed_columns = None
    if state.operation == "select":
        if state.columns and state.columns != "*":
            from ._internal import parse_columns

            parsed_columns = parse_columns(state.columns)
            body["columns"] = [p.col for p in parsed_columns]
        if state.select_count is not None:
            body["count"] = state.select_count
        if state.select_head is not None:
            body["head"] = state.select_head
        if state.joins:
            body["joins"] = [
                {"table": j.table, "on": j.on, **({"type": j.type} if j.type else {})}
                for j in state.joins
            ]

    if state.operation in ("select", "update", "delete"):
        from ._internal import filters_to_dicts

        if state.filters:
            body["filters"] = filters_to_dicts(state.filters)
        if state.or_filters:
            body["orFilters"] = [filters_to_dicts(group) for group in state.or_filters]
        if state.not_filters:
            body["notFilters"] = state.not_filters

    if state.operation in ("insert", "upsert"):
        body["data"] = state.insert_data
        if state.upsert_on_conflict:
            body["onConflict"] = state.upsert_on_conflict

    if state.operation == "update":
        body["data"] = state.update_data

    if state.order_by:
        body["order"] = [
            {
                "column": o.column,
                **({"ascending": o.ascending} if o.ascending is not None else {}),
                **({"nullsFirst": o.nulls_first} if o.nulls_first is not None else {}),
            }
            for o in state.order_by
        ]
    if state.limit_ is not None:
        body["limit"] = state.limit_
    if state.offset_ is not None:
        body["offset"] = state.offset_
    if state.range_ is not None:
        body["range"] = state.range_
    if state.returning:
        body["returning"] = state.returning

    return body
