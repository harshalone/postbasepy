# postbase-py

The official Python client for [Postbase](https://www.getpostbase.com) — a self-hosted, open-source backend as a service.

[![PyPI version](https://img.shields.io/pypi/v/postbase)](https://pypi.org/project/postbase/)
[![license](https://img.shields.io/pypi/l/postbase)](https://github.com/harshalone/postbase/blob/main/LICENSE)

> **[getpostbase.com](https://www.getpostbase.com)** · [Documentation](https://www.getpostbase.com/docs) · [GitHub](https://github.com/harshalone/postbase)

---

## What is Postbase?

Postbase is a self-hosted backend platform built on PostgreSQL. It gives you a database with a REST query API, authentication (password, magic link, OTP, OAuth), file storage, and row-level security — all running on your own infrastructure.

`postbase` is the Python client SDK for interacting with your Postbase instance — sync and async, with the same chainable query builder as [`postbasejs`](https://www.npmjs.com/package/postbasejs).

---

## Installation

```bash
pip install postbase
# or
uv add postbase
# or
poetry add postbase
```

Requires Python 3.9+. Built on [`httpx`](https://www.python-httpx.org/), so both sync and async clients share one dependency.

---

## Quick Start

**Sync:**

```python
from postbase import create_client

postbase = create_client(
    "https://your-postbase-instance.com",
    "pb_anon_your_api_key",
    project_id="your-project-id",
)

result = postbase.from_("posts").select().execute()
print(result.data, result.error)
```

**Async:**

```python
from postbase.aio import create_async_client

postbase = create_async_client(
    "https://your-postbase-instance.com",
    "pb_anon_your_api_key",
    project_id="your-project-id",
)

result = await postbase.from_("posts").select().execute()
print(result.data, result.error)
```

Your **URL**, **anon key**, and **project ID** can be found in the API Keys section of your Postbase dashboard.

Every module in `postbase.aio` mirrors its sync counterpart in `postbase` method-for-method — only the client construction (`create_async_client`) and the `await` on each call differ. The rest of this README shows sync examples; add `await` and import from `postbase.aio` to use the async client.

---

## Database

Query your PostgreSQL tables with a fluent, chainable API. Query builders are lazy — nothing is sent until you call `.execute()`, `.single()`, or `.maybe_single()` (or `await` an async builder directly, which does an implicit `.execute()`).

### Select

```python
# Fetch all posts (wildcard or omit argument — both work)
result = postbase.from_("posts").select("*").execute()
result = postbase.from_("posts").select().execute()

# Select specific columns
result = postbase.from_("posts").select("id, title, created_at").execute()

# With filters
result = (
    postbase.from_("posts")
    .select("*")
    .eq("status", "published")
    .order("created_at", ascending=False)
    .limit(10)
    .execute()
)

# Get total count
result = postbase.from_("posts").select("*", count="exact").execute()
print(result.count)
```

### Filter methods

Available on `select()`, `update()`, and `delete()` chains.

| Method | SQL equivalent |
|---|---|
| `.eq(col, val)` | `col = val` |
| `.neq(col, val)` | `col != val` |
| `.gt(col, val)` | `col > val` |
| `.gte(col, val)` | `col >= val` |
| `.lt(col, val)` | `col < val` |
| `.lte(col, val)` | `col <= val` |
| `.like(col, pattern)` | `col LIKE pattern` |
| `.ilike(col, pattern)` | `col ILIKE pattern` |
| `.in_(col, values)` | `col IN (values)` |
| `.is_(col, None \| bool)` | `col IS NULL / TRUE / FALSE` |
| `.contains(col, val)` | `col @> val` |
| `.overlaps(col, val)` | `col && val` |
| `.text_search(col, query)` | full-text search |
| `.or_(filters)` | `col = val OR col = val` |
| `.not_(col, op, val)` | `NOT col op val` |

> `in_`, `is_`, `or_`, and `not_` have a trailing underscore — `in`, `is`, `or`, and `not` are Python keywords.

### `.or_()` — Supabase-compatible filter string

Pass a Supabase-style filter string and the SDK parses it into structured filters before sending to the server. Commas separate OR conditions; values with commas are safe inside parentheses (used by `in`).

```python
# Simple OR: match either condition
result = postbase.from_("users").select().or_("email.ilike.%alice%,name.ilike.%alice%").execute()

# OR with in operator — values in parens are safe
result = postbase.from_("orders").select().or_("status.eq.active,status.in.(pending,review)").execute()

# Combine OR with AND filters — the .eq() is ANDed with the OR group
result = (
    postbase.from_("posts")
    .select()
    .eq("published", True)
    .or_("title.ilike.%hello%,body.ilike.%hello%")
    .execute()
)
```

**Supported operators inside `.or_()`:** `eq` `neq` `gt` `gte` `lt` `lte` `like` `ilike` `in` `is`

### Joins

Use `.join()` to combine data from related tables. Builders are immutable and can be stacked.

```python
# Left join — include orders even if no matching user
result = (
    postbase.from_("orders")
    .join("users", on="orders.user_id = users.id", type="left")
    .select("orders.id, orders.total, users.email")
    .execute()
)

# Multiple joins
result = (
    postbase.from_("orders")
    .join("users", on="orders.user_id = users.id", type="left")
    .join("products", on="orders.product_id = products.id")
    .select("orders.id, users.email, products.name")
    .eq("orders.status", "active")
    .order("orders.created_at", ascending=False)
    .limit(20)
    .execute()
)
```

**Join types** (`type` defaults to `"inner"` if omitted): `"inner"`, `"left"`, `"right"`, `"full"`.

**`on` expression rules** — the server validates the `on` string against a strict allow-list:

- `table.column = table.column`
- Comparison operators: `=`, `<`, `>`, `!=`, `<=`, `>=`
- Identifiers and dotted column references only — no raw SQL, no functions, no subqueries

```python
# Valid
postbase.from_("orders").join("users", on="orders.user_id = users.id")

# Invalid — rejected by the server
postbase.from_("orders").join("users", on="orders.user_id = users.id AND users.active = true")
```

**Column aliases** — when two joined tables share a column name (e.g. both have `id`), use `AS` to rename them. The SDK strips the alias before sending to the server and renames the keys in the returned rows client-side.

```python
result = (
    postbase.from_("apis")
    .join("pricing_plans", on="apis.pricing_plan_id = pricing_plans.id", type="left")
    .select("apis.id as api_id, apis.name, pricing_plans.id as plan_id, pricing_plans.name as plan_name")
    .execute()
)
# result.data[0] == {"api_id": "...", "name": "...", "plan_id": "...", "plan_name": "..."}
```

> **Limitation:** if you select two columns with the same base name without aliasing both (e.g. `apis.id, pricing_plans.id`), the server collapses them to one `id` key before the SDK sees the response — only one value survives. Always alias at least all but one of any colliding columns.

---

### Raw SQL

For queries that can't be expressed with the builder (CTEs, window functions, complex aggregates), use `postbase.sql()`. RLS context is still enforced — the authenticated user's JWT is forwarded exactly as with `.from_()`.

```python
result = postbase.sql(
    """
    SELECT o.id, u.email
    FROM orders o
    INNER JOIN users u ON o.user_id = u.id
    WHERE o.status = $1
    """,
    ["active"],
)

# Multiple params
result = postbase.sql(
    """
    SELECT p.title, COUNT(c.id) AS count
    FROM posts p
    LEFT JOIN comments c ON c.post_id = p.id
    WHERE p.author_id = $1 AND p.status = $2
    GROUP BY p.id, p.title
    ORDER BY count DESC
    LIMIT $3
    """,
    [user_id, "published", 10],
)
```

Params replace `$1`, `$2`, `$3`, … placeholders (standard PostgreSQL positional parameters). Never interpolate values directly into the query string — always use params to prevent SQL injection.

---

### Insert

```python
result = postbase.from_("posts").insert({"title": "Hello World", "status": "draft"}).select().single()
```

### Update

```python
result = (
    postbase.from_("posts")
    .update({"status": "published"})
    .eq("id", "post-id")
    .select()
    .single()
)
```

### Upsert

```python
result = (
    postbase.from_("profiles")
    .upsert({"id": "user-id", "username": "alice"}, on_conflict="id")
    .select()
    .execute()
)
```

### Delete

```python
result = postbase.from_("posts").delete().eq("id", "post-id").execute()
```

### Single row helpers

```python
# Errors if not exactly one row
result = postbase.from_("posts").select("*").eq("id", post_id).single()

# Returns None if not found (no error)
result = postbase.from_("posts").select("*").eq("id", post_id).maybe_single()
```

### Pagination

```python
# Limit + offset
result = postbase.from_("posts").select("*").limit(20).offset(40).execute()

# Range (inclusive)
result = postbase.from_("posts").select("*").range(0, 19).execute()
```

---

## Authentication

### Sign up

```python
response = postbase.auth.sign_up("user@example.com", "supersecret", remember_me=True)
# response.user, response.session, response.error
```

### Sign in with password

```python
response = postbase.auth.sign_in_with_password("user@example.com", "supersecret", remember_me=True)
```

### OTP & Magic Link (passwordless)

**Magic link:**

```python
postbase.auth.sign_in_with_otp("user@example.com", type="magic_link", redirect_to="https://yourapp.com/dashboard")
```

**6-digit OTP code:**

```python
# 1. Request the code
postbase.auth.sign_in_with_otp("user@example.com", type="otp")

# 2. Verify the code
response = postbase.auth.verify_otp("user@example.com", "123456", remember_me=True)
# response.user, response.session
```

### Email OTP (the `/email-otp` flow)

```python
postbase.auth.sign_in_with_email_otp("user@example.com")
response = postbase.auth.verify_email_otp("user@example.com", "123456", remember_me=True)
```

### OAuth (redirect-based, PKCE)

There's no browser in a Python backend to redirect for you — build the authorize URL, issue the HTTP redirect yourself in your framework's route handler, and persist `code_verifier` / `state` (e.g. in a server-side session) so you can complete the flow on callback:

```python
oauth = postbase.auth.get_oauth_sign_in_url(
    "google",
    redirect_to="https://yourapp.com/auth/callback",
)
# oauth["url"]           -> redirect the user here
# oauth["code_verifier"] -> stash in session/cookie, needed nowhere else since
#                            Postbase's server completes the PKCE exchange itself
# oauth["state"]         -> CSRF token embedded in the redirect

# In your framework, return a redirect response to oauth["url"].
```

### Handle OAuth callback

Postbase's OAuth callback redirects back to your `redirect_to` URL with session tokens as query params. Pass the full callback URL your route handler received:

```python
# e.g. in a FastAPI/Flask/Django view for /auth/callback
response = postbase.auth.handle_oauth_callback(str(request.url))
# response.session, response.user, response.error
```

### Sign in with Apple / Google (native id_token — no browser)

For mobile/native apps that hand you an `id_token` directly from the platform SDK, skip the browser redirect entirely:

```python
response = postbase.auth.sign_in_with_id_token(
    provider="apple",
    id_token=apple_identity_token,
    nonce=nonce,          # optional — include if you passed a nonce to the native request
    remember_me=True,
)

response = postbase.auth.sign_in_with_id_token(
    provider="google",
    id_token=google_id_token,
    remember_me=True,
)
```

> **Note:** the provider must be enabled in your Postbase dashboard. The `clientId` field should contain your Apple Service ID (for web) or comma-separated Bundle IDs (for native), matching the `aud` claim in Apple's `id_token`.

### Remember me

`remember_me=True` issues a 30-day refresh token instead of the default 7-day one. The flag is stored on the session row server-side, so it's carried forward automatically on every subsequent `refresh_session()` call — no need to keep resending it.

Supported directly (single call, no follow-up needed) on `sign_up`, `sign_in_with_password`, `verify_otp`, `verify_email_otp`, and `sign_in_with_id_token`.

**Redirect-based OAuth is the one exception** — the tokens come back as URL query params on the callback, not from a call you control, so there's no request body to put `remember_me` in. Use `set_remember_me` afterwards instead:

```python
response = postbase.auth.set_remember_me(True)
# response.session.refresh_token is now valid for 30 days
```

### Get current user / session

```python
user_result = postbase.auth.get_user()
# user_result["data"]["user"], user_result["error"]

session_result = postbase.auth.get_session()
# session_result["data"]["session"], session_result["error"]
```

> `session.expires_at` is the **access token's** expiry (short-lived, ~1 hour). `session.refresh_token_expires_at` is the **refresh token's** expiry (7 or 30 days depending on `remember_me`) — this is what `set_session()` uses for the cookie's `max_age` in SSR contexts. Don't use `expires_at` to reason about how long the user stays logged in.

### Sign out

```python
postbase.auth.sign_out()
```

### Update user

```python
postbase.auth.update_user(name="Alice", data={"plan": "pro"})
```

### Listen to auth state changes

```python
def on_change(event, session):
    # event: "SIGNED_IN" | "SIGNED_OUT" | "TOKEN_REFRESHED" | "USER_UPDATED"
    print(event, session)

sub = postbase.auth.on_auth_state_change(on_change)
sub.unsubscribe()
```

### Admin (service role key required)

```python
admin_client = create_client(url, "pb_service_your_service_key", project_id="your-project-id")

# List users
result = admin_client.auth.admin.list_users(page=1, per_page=50)

# Create user
result = admin_client.auth.admin.create_user(
    email="new@example.com",
    password="password",
    email_confirm=True,
)

# Update / delete user
admin_client.auth.admin.update_user_by_id(user_id, email="new@example.com")
admin_client.auth.admin.delete_user(user_id)
```

---

## Storage

### Upload a file

Pass `content_type` to ensure the correct MIME type is stored with the file — required for binary uploads (PNG, PDF, etc.). Accepts raw `bytes` or any file-like object exposing `.read()`.

```python
with open("avatar.png", "rb") as f:
    result = postbase.storage.from_("avatars").upload("user-123.png", f, content_type="image/png")
# result.data == {"path": "...", "fullPath": "..."}

# Or pass bytes directly
result = postbase.storage.from_("avatars").upload("user-123.png", image_bytes, content_type="image/png")

# Upsert (overwrite an existing file)
result = postbase.storage.from_("avatars").upload(
    "user-123.png", image_bytes, content_type="image/png", upsert=True
)
```

### Get public URL

```python
result = postbase.storage.from_("avatars").get_public_url("user-123.png")
# result["data"]["publicUrl"]
```

### Download a file

```python
result = postbase.storage.from_("avatars").download("user-123.png")
# result["data"] is raw bytes
```

### Create a signed URL (temporary access)

```python
result = postbase.storage.from_("private-docs").create_signed_url("report.pdf", 3600)  # 1 hour
# result.data["signedUrl"]
```

### List files

```python
result = postbase.storage.from_("avatars").list("folder/", limit=100, sort_by_column="name")
```

### Delete files

```python
postbase.storage.from_("avatars").remove(["user-123.png", "user-456.png"])
```

### Move / Copy

```python
postbase.storage.from_("docs").move("old-name.pdf", "new-name.pdf")
postbase.storage.from_("docs").copy("template.pdf", "copy.pdf")
```

### Bucket management

```python
# Create
postbase.storage.create_bucket(
    "avatars",
    public=True,
    file_size_limit=5 * 1024 * 1024,  # 5 MB
    allowed_mime_types=["image/png", "image/jpeg"],
)

# List
buckets = postbase.storage.list_buckets()

# Update
postbase.storage.update_bucket("avatars", public=False)

# Delete
postbase.storage.delete_bucket("avatars")

# Empty (delete all objects)
postbase.storage.empty_bucket("avatars")
```

---

## RPC (PostgreSQL functions)

Call a stored procedure or function in your project's schema:

```python
result = postbase.rpc("get_nearby_posts", {"lat": 37.7749, "lng": -122.4194, "radius": 10})
```

---

## Email

Send a transactional email using your project's configured email provider (e.g. AWS SES).

```python
result = postbase.email.send(
    to="user@example.com",
    subject="Welcome!",
    text="Hello there",
    html="<p>Hello there</p>",
    reply_to="support@example.com",  # optional
)
# result["data"]["ok"]
```

---

## SSR / server-side session forwarding

When running behind a web framework (FastAPI, Flask, Django, etc.), you can forward the caller's session cookie to Postbase so RLS policies evaluate against the authenticated user instead of just the anon role. Implement a `CookieAdapter` bridging your framework's request/response to Postbase:

```python
from postbase import CookieAdapter, Cookie, create_client

def get_all():
    # Read cookies off the incoming request (framework-specific)
    return [Cookie(name=name, value=value) for name, value in request.cookies.items()]

def set_all(cookies_to_set):
    # Write cookies onto the outgoing response (framework-specific)
    for c in cookies_to_set:
        response.set_cookie(c.name, c.value, **c.options)

postbase = create_client(
    url, anon_key,
    project_id=project_id,
    cookies=CookieAdapter(get_all=get_all, set_all=set_all),
)

result = postbase.from_("posts").select().execute()  # RLS applies to the signed-in user
```

`get_all`/`set_all` may be sync or async callables — `AsyncClient` awaits them automatically if they return an awaitable; the sync `Client` requires plain (non-async) callables.

The session cookie is named `postbase-session`. After completing an OAuth flow or otherwise obtaining a session outside the normal sign-in calls, persist it with `auth.set_session(session)` — this writes the `postbase-session` httpOnly cookie via your `CookieAdapter.set_all`, so subsequent requests using the same adapter are authenticated automatically.

```python
error = postbase.auth.set_session(session)["error"]
```

---

## Row Level Security (RLS)

When a user is signed in (via a forwarded `X-Postbase-Token`/session cookie), their session JWT is automatically forwarded with every query. Your RLS policies can reference the user via:

```sql
current_setting('postbase.user_id', true)  -- the authenticated user's ID
current_setting('postbase.role', true)     -- the user's role
```

Example policy — users can only read their own rows:

```sql
CREATE POLICY "own rows" ON posts
  FOR SELECT USING (
    user_id = current_setting('postbase.user_id', true)::uuid
  );
```

---

## Environment Variables

We recommend storing your Postbase credentials in environment variables:

```bash
POSTBASE_URL=https://your-postbase-instance.com
POSTBASE_ANON_KEY=pb_anon_...
POSTBASE_PROJECT_ID=your-project-id
# Service key — server-side only, bypasses RLS
POSTBASE_SERVICE_KEY=pb_service_...
```

Use your **service role key** (`pb_service_...`) only in trusted server-side code — it bypasses RLS.

---

## Sync vs. async

| | `postbase` | `postbase.aio` |
|---|---|---|
| Client factory | `create_client(...)` | `create_async_client(...)` |
| HTTP backend | `httpx.Client` | `httpx.AsyncClient` |
| Call style | `result = postbase.from_("t").select().execute()` | `result = await postbase.from_("t").select().execute()` |
| Awaiting a builder directly | not supported — call `.execute()` | `await postbase.from_("t").select()` implicitly executes |
| Context manager | `with create_client(...) as postbase:` | `async with create_async_client(...) as postbase:` |

Both share the same method names, arguments, and return shapes (`QueryResult`, `SingleResult`, `AuthResponse`, dataclasses) — only sync/async mechanics differ.

---

## Type hints

The SDK is fully type-annotated. Query results are `QueryResult[T]` / `SingleResult[T]` dataclasses:

```python
from dataclasses import dataclass
from postbase import create_client

@dataclass
class Post:
    id: str
    title: str
    status: str
    created_at: str

postbase = create_client(url, key, project_id=project_id)
result = postbase.from_("posts").select().eq("status", "published").execute()
# result.data is a list[dict] — construct your dataclass from each row as needed:
posts = [Post(**row) for row in (result.data or [])]
```

---

## License

MIT — see [LICENSE](LICENSE).

---

Built with love by the [Postbase](https://www.getpostbase.com) team.
