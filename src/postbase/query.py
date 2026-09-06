"""Synchronous query builder for the `/api/db/query` endpoint."""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

import httpx

from ._internal import apply_aliases, parse_columns, parse_or_filter_string
from ._query_state import QueryState, build_request_body
from .types import Filter, FilterOperator, JoinClause, JoinType, OrderBy, QueryResult, SingleResult

T = TypeVar("T")


def _execute(client: httpx.Client, state: QueryState) -> QueryResult[Dict[str, Any]]:
    if not state.base_url:
        raise ValueError(
            "[postbase] url is required — ensure POSTBASE_URL is set in your environment"
        )
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {state.api_key}",
        **state.extra_headers,
    }
    if state.session_token:
        headers["X-Postbase-Session"] = state.session_token

    body = build_request_body(state)

    try:
        res = client.post(f"{state.base_url}/api/db/query", headers=headers, json=body)
        json_body = res.json()
    except Exception as err:  # noqa: BLE001 - surfaced as an error result, not raised
        return QueryResult(data=None, count=None, error=str(err))

    if res.is_error:
        return QueryResult(data=None, count=None, error=json_body.get("error", "Query failed"))

    raw_data: List[Dict[str, Any]] = json_body.get("data") or []
    if state.operation == "select" and state.columns and state.columns != "*":
        parsed = parse_columns(state.columns)
        raw_data = apply_aliases(raw_data, parsed)
    return QueryResult(data=raw_data, count=json_body.get("count"), error=None)


class _FilterMixin:
    """Shared filter/order chaining methods, implemented via `_with_state`."""

    _state: QueryState

    def _with_state(self, state: QueryState) -> Any:
        raise NotImplementedError

    def _add_filter(self, column: str, operator: FilterOperator, value: Any) -> Any:
        return self._with_state(
            self._state.evolve(filters=[*self._state.filters, Filter(column, operator, value)])
        )

    def eq(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "eq", value)

    def neq(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "neq", value)

    def gt(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "gt", value)

    def gte(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "gte", value)

    def lt(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "lt", value)

    def lte(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "lte", value)

    def like(self, column: str, pattern: str) -> Any:
        return self._add_filter(column, "like", pattern)

    def ilike(self, column: str, pattern: str) -> Any:
        return self._add_filter(column, "ilike", pattern)

    def in_(self, column: str, values: List[Any]) -> Any:
        return self._add_filter(column, "in", values)

    def is_(self, column: str, value: Optional[bool]) -> Any:
        return self._add_filter(column, "is", value)

    def contains(self, column: str, value: Any) -> Any:
        return self._add_filter(column, "contains", value)

    def overlaps(self, column: str, value: List[Any]) -> Any:
        return self._add_filter(column, "overlaps", value)

    def text_search(self, column: str, query: str, config: Optional[str] = None) -> Any:
        return self._add_filter(column, "textSearch", {"query": query, "config": config})

    def or_(self, filters: str) -> Any:
        return self._with_state(
            self._state.evolve(
                or_filters=[*self._state.or_filters, parse_or_filter_string(filters)]
            )
        )

    def not_(self, column: str, operator: str, value: Any) -> Any:
        return self._with_state(
            self._state.evolve(
                not_filters=[
                    *self._state.not_filters,
                    {"column": column, "operator": operator, "value": value},
                ]
            )
        )


class QueryBuilder(_FilterMixin, Generic[T]):
    def __init__(self, http: httpx.Client, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> QueryBuilder[T]:
        return QueryBuilder(self._http, state)

    def select(
        self,
        columns: str = "*",
        count: Optional[str] = None,
        head: Optional[bool] = None,
    ) -> QueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                columns=columns, select_count=count, select_head=head, operation="select"
            )
        )

    def join(self, table: str, on: str, type: Optional[JoinType] = None) -> QueryBuilder[T]:
        return self._with_state(
            self._state.evolve(joins=[*self._state.joins, JoinClause(table, on, type)])
        )

    def order(
        self,
        column: str,
        ascending: Optional[bool] = None,
        nulls_first: Optional[bool] = None,
    ) -> QueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                order_by=[*self._state.order_by, OrderBy(column, ascending, nulls_first)]
            )
        )

    def limit(self, count: int) -> QueryBuilder[T]:
        return self._with_state(self._state.evolve(limit_=count))

    def offset(self, count: int) -> QueryBuilder[T]:
        return self._with_state(self._state.evolve(offset_=count))

    def range(self, from_: int, to: int) -> QueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                range_={"from": from_, "to": to}, limit_=to - from_ + 1, offset_=from_
            )
        )

    def insert(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        returning: str = "*",
    ) -> InsertBuilder[T]:
        return InsertBuilder(
            self._http,
            self._state.evolve(operation="insert", insert_data=data, returning=returning),
        )

    def upsert(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        on_conflict: Optional[str] = None,
        returning: str = "*",
    ) -> InsertBuilder[T]:
        return InsertBuilder(
            self._http,
            self._state.evolve(
                operation="upsert",
                insert_data=data,
                upsert_on_conflict=on_conflict,
                returning=returning,
            ),
        )

    def update(self, data: Dict[str, Any]) -> UpdateBuilder[T]:
        return UpdateBuilder(
            self._http, self._state.evolve(operation="update", update_data=data, returning="*")
        )

    def delete(self) -> DeleteBuilder[T]:
        return DeleteBuilder(self._http, self._state.evolve(operation="delete", returning="*"))

    def execute(self) -> QueryResult[T]:
        return _execute(self._http, self._state)  # type: ignore[return-value]

    def single(self) -> SingleResult[T]:
        result = _execute(self._http, self._state.evolve(limit_=1))
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        if len(rows) == 0:
            return SingleResult(data=None, error="No rows returned")
        if len(rows) > 1:
            return SingleResult(data=None, error="Multiple rows returned")
        return SingleResult(data=rows[0], error=None)  # type: ignore[arg-type]

    def maybe_single(self) -> SingleResult[T]:
        result = _execute(self._http, self._state.evolve(limit_=1))
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        return SingleResult(data=(rows[0] if rows else None), error=None)  # type: ignore[arg-type]

    def __await__(self) -> Any:
        raise TypeError("QueryBuilder is not awaitable — call .execute() or use AsyncQueryBuilder")


class _TerminalBuilderMixin(_FilterMixin, Generic[T]):
    _http: httpx.Client
    _state: QueryState

    def select(self, columns: str = "*") -> Any:
        return self._with_state(self._state.evolve(returning=columns))

    def execute(self) -> QueryResult[T]:
        return _execute(self._http, self._state)  # type: ignore[return-value]

    def single(self) -> SingleResult[T]:
        result = _execute(self._http, self._state)
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        return SingleResult(data=(rows[0] if rows else None), error=None)  # type: ignore[arg-type]


class InsertBuilder(_TerminalBuilderMixin[T]):
    def __init__(self, http: httpx.Client, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> InsertBuilder[T]:
        return InsertBuilder(self._http, state)


class UpdateBuilder(_TerminalBuilderMixin[T]):
    def __init__(self, http: httpx.Client, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> UpdateBuilder[T]:
        return UpdateBuilder(self._http, state)


class DeleteBuilder(_TerminalBuilderMixin[T]):
    def __init__(self, http: httpx.Client, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> DeleteBuilder[T]:
        return DeleteBuilder(self._http, state)
