"""Shared types for the Postbase Python client."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import (
    Any,
    Awaitable,
    Callable,
    Dict,
    Generic,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
)

T = TypeVar("T")

FilterOperator = Literal[
    "eq",
    "neq",
    "gt",
    "gte",
    "lt",
    "lte",
    "like",
    "ilike",
    "in",
    "is",
    "contains",
    "overlaps",
    "textSearch",
]

JoinType = Literal["inner", "left", "right", "full"]

RealtimeEvent = Literal["INSERT", "UPDATE", "DELETE", "*"]

AuthChangeEvent = Literal["SIGNED_IN", "SIGNED_OUT", "TOKEN_REFRESHED", "USER_UPDATED"]

NativeOAuthProvider = Literal["apple", "google"]


@dataclass(frozen=True)
class Filter:
    column: str
    operator: FilterOperator
    value: Any


@dataclass(frozen=True)
class JoinClause:
    table: str
    on: str
    type: Optional[JoinType] = None


@dataclass(frozen=True)
class OrderBy:
    column: str
    ascending: Optional[bool] = None
    nulls_first: Optional[bool] = None


@dataclass
class QueryResult(Generic[T]):
    data: Optional[List[T]]
    count: Optional[int]
    error: Optional[str]


@dataclass
class SingleResult(Generic[T]):
    data: Optional[T]
    error: Optional[str]


@dataclass(frozen=True)
class AuthUser:
    id: str
    email: str
    name: Optional[str] = None
    image: Optional[str] = None
    email_verified: Optional[bool] = None
    phone: Optional[str] = None
    role: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional[AuthUser]:
        if not data:
            return None
        return cls(
            id=data.get("id", ""),
            email=data.get("email", ""),
            name=data.get("name"),
            image=data.get("image"),
            email_verified=data.get("emailVerified"),
            phone=data.get("phone"),
            role=data.get("role"),
            metadata=data.get("metadata") or {},
            created_at=data.get("createdAt"),
            updated_at=data.get("updatedAt"),
        )


@dataclass(frozen=True)
class Session:
    access_token: str
    expires_at: float
    refresh_token: Optional[str] = None
    refresh_token_expires_at: Optional[float] = None
    user: Optional[AuthUser] = None

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional[Session]:
        if not data:
            return None
        return cls(
            access_token=data.get("accessToken", ""),
            expires_at=data.get("expiresAt", 0),
            refresh_token=data.get("refreshToken"),
            refresh_token_expires_at=data.get("refreshTokenExpiresAt"),
            user=AuthUser.from_dict(data.get("user")),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "accessToken": self.access_token,
            "expiresAt": self.expires_at,
            "refreshToken": self.refresh_token,
            "refreshTokenExpiresAt": self.refresh_token_expires_at,
            "user": (
                None
                if self.user is None
                else {
                    "id": self.user.id,
                    "email": self.user.email,
                    "name": self.user.name,
                    "image": self.user.image,
                    "emailVerified": self.user.email_verified,
                    "phone": self.user.phone,
                    "role": self.user.role,
                    "metadata": self.user.metadata,
                    "createdAt": self.user.created_at,
                    "updatedAt": self.user.updated_at,
                }
            ),
        }


@dataclass
class AuthResponse:
    user: Optional[AuthUser]
    session: Optional[Session]
    error: Optional[str]


@dataclass(frozen=True)
class StorageObject:
    name: str
    size: int
    content_type: str
    updated_at: str
    created_at: str


@dataclass(frozen=True)
class Bucket:
    id: str
    name: str
    public: bool
    created_at: str
    updated_at: str
    file_size_limit: Optional[int] = None
    allowed_mime_types: Optional[List[str]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> Bucket:
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            public=bool(data.get("public", False)),
            created_at=data.get("createdAt", ""),
            updated_at=data.get("updatedAt", ""),
            file_size_limit=data.get("fileSizeLimit"),
            allowed_mime_types=data.get("allowedMimeTypes"),
        )


@dataclass(frozen=True)
class RealtimePayload(Generic[T]):
    event_type: RealtimeEvent
    new: Optional[T]
    old: Optional[T]
    schema: str
    table: str
    commit_timestamp: str


# A cookie as read from the host framework's request.
@dataclass(frozen=True)
class Cookie:
    name: str
    value: str


# A cookie to be set on the host framework's response.
@dataclass(frozen=True)
class CookieToSet:
    name: str
    value: str
    options: Dict[str, Any] = field(default_factory=dict)


GetAllCookies = Callable[[], Union[List[Cookie], Awaitable[List[Cookie]]]]
SetAllCookies = Callable[[List[CookieToSet]], Union[None, Awaitable[None]]]


@dataclass(frozen=True)
class CookieAdapter:
    """Bridges Postbase session cookies to a host web framework's request/response.

    ``get_all`` and ``set_all`` may be sync or async callables — the SSR client
    awaits them if they return an awaitable.
    """

    get_all: GetAllCookies
    set_all: SetAllCookies
