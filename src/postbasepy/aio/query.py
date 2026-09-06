"""Asynchronous query builder for the `/api/db/query` endpoint."""

from __future__ import annotations

from typing import Any, Dict, Generic, List, Optional, TypeVar, Union

import httpx

from .._internal import apply_aliases, parse_columns, parse_or_filter_string
from .._query_state import QueryState, build_request_body
from ..types import Filter, FilterOperator, JoinClause, JoinType, OrderBy, QueryResult, SingleResult

T = TypeVar("T")


async def _execute(client: httpx.AsyncClient, state: QueryState) -> QueryResult[Dict[str, Any]]:
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
        res = await client.post(f"{state.base_url}/api/db/query", headers=headers, json=body)
        json_body = res.json()
    except Exception as err:  # noqa: BLE001
        return QueryResult(data=None, count=None, error=str(err))

    if res.is_error:
        return QueryResult(data=None, count=None, error=json_body.get("error", "Query failed"))

    raw_data: List[Dict[str, Any]] = json_body.get("data") or []
    if state.operation == "select" and state.columns and state.columns != "*":
        parsed = parse_columns(state.columns)
        raw_data = apply_aliases(raw_data, parsed)
    return QueryResult(data=raw_data, count=json_body.get("count"), error=None)


class _AsyncFilterMixin:
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


class AsyncQueryBuilder(_AsyncFilterMixin, Generic[T]):
    def __init__(self, http: httpx.AsyncClient, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> AsyncQueryBuilder[T]:
        return AsyncQueryBuilder(self._http, state)

    def select(
        self,
        columns: str = "*",
        count: Optional[str] = None,
        head: Optional[bool] = None,
    ) -> AsyncQueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                columns=columns, select_count=count, select_head=head, operation="select"
            )
        )

    def join(self, table: str, on: str, type: Optional[JoinType] = None) -> AsyncQueryBuilder[T]:
        return self._with_state(
            self._state.evolve(joins=[*self._state.joins, JoinClause(table, on, type)])
        )

    def order(
        self,
        column: str,
        ascending: Optional[bool] = None,
        nulls_first: Optional[bool] = None,
    ) -> AsyncQueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                order_by=[*self._state.order_by, OrderBy(column, ascending, nulls_first)]
            )
        )

    def limit(self, count: int) -> AsyncQueryBuilder[T]:
        return self._with_state(self._state.evolve(limit_=count))

    def offset(self, count: int) -> AsyncQueryBuilder[T]:
        return self._with_state(self._state.evolve(offset_=count))

    def range(self, from_: int, to: int) -> AsyncQueryBuilder[T]:
        return self._with_state(
            self._state.evolve(
                range_={"from": from_, "to": to}, limit_=to - from_ + 1, offset_=from_
            )
        )

    def insert(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        returning: str = "*",
    ) -> AsyncInsertBuilder[T]:
        return AsyncInsertBuilder(
            self._http,
            self._state.evolve(operation="insert", insert_data=data, returning=returning),
        )

    def upsert(
        self,
        data: Union[Dict[str, Any], List[Dict[str, Any]]],
        on_conflict: Optional[str] = None,
        returning: str = "*",
    ) -> AsyncInsertBuilder[T]:
        return AsyncInsertBuilder(
            self._http,
            self._state.evolve(
                operation="upsert",
                insert_data=data,
                upsert_on_conflict=on_conflict,
                returning=returning,
            ),
        )

    def update(self, data: Dict[str, Any]) -> AsyncUpdateBuilder[T]:
        return AsyncUpdateBuilder(
            self._http, self._state.evolve(operation="update", update_data=data, returning="*")
        )

    def delete(self) -> AsyncDeleteBuilder[T]:
        return AsyncDeleteBuilder(self._http, self._state.evolve(operation="delete", returning="*"))

    async def execute(self) -> QueryResult[T]:
        return await _execute(self._http, self._state)  # type: ignore[return-value]

    async def single(self) -> SingleResult[T]:
        result = await _execute(self._http, self._state.evolve(limit_=1))
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        if len(rows) == 0:
            return SingleResult(data=None, error="No rows returned")
        if len(rows) > 1:
            return SingleResult(data=None, error="Multiple rows returned")
        return SingleResult(data=rows[0], error=None)  # type: ignore[arg-type]

    async def maybe_single(self) -> SingleResult[T]:
        result = await _execute(self._http, self._state.evolve(limit_=1))
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        return SingleResult(data=(rows[0] if rows else None), error=None)  # type: ignore[arg-type]

    def __await__(self) -> Any:
        return self.execute().__await__()


class _AsyncTerminalBuilderMixin(_AsyncFilterMixin, Generic[T]):
    _http: httpx.AsyncClient
    _state: QueryState

    def select(self, columns: str = "*") -> Any:
        return self._with_state(self._state.evolve(returning=columns))

    async def execute(self) -> QueryResult[T]:
        return await _execute(self._http, self._state)  # type: ignore[return-value]

    async def single(self) -> SingleResult[T]:
        result = await _execute(self._http, self._state)
        if result.error:
            return SingleResult(data=None, error=result.error)
        rows = result.data or []
        return SingleResult(data=(rows[0] if rows else None), error=None)  # type: ignore[arg-type]

    def __await__(self) -> Any:
        return self.execute().__await__()


class AsyncInsertBuilder(_AsyncTerminalBuilderMixin[T]):
    def __init__(self, http: httpx.AsyncClient, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> AsyncInsertBuilder[T]:
        return AsyncInsertBuilder(self._http, state)


class AsyncUpdateBuilder(_AsyncTerminalBuilderMixin[T]):
    def __init__(self, http: httpx.AsyncClient, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> AsyncUpdateBuilder[T]:
        return AsyncUpdateBuilder(self._http, state)


class AsyncDeleteBuilder(_AsyncTerminalBuilderMixin[T]):
    def __init__(self, http: httpx.AsyncClient, state: QueryState) -> None:
        self._http = http
        self._state = state

    def _with_state(self, state: QueryState) -> AsyncDeleteBuilder[T]:
        return AsyncDeleteBuilder(self._http, state)
