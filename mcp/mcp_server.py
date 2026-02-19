"""
MCP server for OpenJDK mailing list search.

Exposes the OpenJDK Mail Search API as tools so AI assistants (e.g. Cursor)
can search and browse OpenJDK mailing list archives. Includes a tool to
fetch raw message content from mail.openjdk.org (the REST API returns only
metadata).

Run with stdio transport for Cursor:
  cd mcp && python -m mcp_server

Or: cd mcp && uv run openjdk-mcp

Requires: pip install mcp httpx (or uv pip install from mcp/)
"""

import asyncio
import html
import json
import os
import re
import unicodedata
import urllib.parse
from typing import Any

import httpx

# When including content in search/list results, cap at this many bodies to keep response size bounded.
MAX_INCLUDE_CONTENT = 5

# Raw mail content is fetched from OpenJDK pipermail (not from the REST API).
PIPERMAIL_BASE = os.environ.get(
    "OPENJDK_PIPERMAIL_BASE_URL", "https://mail.openjdk.org/pipermail"
)

# Use official MCP Python SDK (pip install mcp)
from mcp.server.fastmcp import FastMCP

BASE_URL = os.environ.get("OPENJDK_MAIL_API_BASE_URL", "https://openjdk.barlasgarden.com/api")

mcp = FastMCP(
    name="OpenJDK Mail Search",
    instructions="Tools for searching and browsing OpenJDK mailing list archives (e.g. net-dev, core-libs-dev, amber-dev). Use when the user asks about OpenJDK lists, mail archives, or specific discussions.",
)


async def _api_get(path: str, query: dict[str, str] | None = None) -> dict[str, Any]:
    url = f"{BASE_URL.rstrip('/')}{path}"
    params = {k: v for k, v in (query or {}).items() if v is not None}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(url, params=params or None)
        resp.raise_for_status()
        return resp.json()


async def _fetch_mail_body(list_name: str, month: str, id_str: str) -> str:
    """Fetch HTML from pipermail and return the message body (first <pre> content)."""
    path = f"{list_name}/{urllib.parse.quote(month)}/{urllib.parse.quote(id_str)}.html"
    url = f"{PIPERMAIL_BASE.rstrip('/')}/{path}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "OpenJDK-Mail-MCP/1.0"})
            resp.raise_for_status()
            html_text = resp.text
    except httpx.HTTPStatusError as e:
        return f"Failed to fetch message: HTTP {e.response.status_code} ({url})"
    except httpx.RequestError as e:
        return f"Failed to fetch message: {e!s}"
    # Pipermail puts the message body in the first <pre> block (tag casing may vary).
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html_text, re.DOTALL | re.IGNORECASE)
    if not m:
        return "No message body found in archive page (page structure may have changed)."
    body = m.group(1).strip()
    body = _sanitize_mail_body(body)
    return body


def _sanitize_mail_body(body: str) -> str:
    """Decode HTML entities and remove control characters that could break parsing or display."""
    body = html.unescape(body)
    # Remove control characters except newline, tab, carriage return (keep normal text flow).
    body = "".join(
        c
        for c in body
        if c in "\n\t\r" or unicodedata.category(c) != "Cc"
    )
    return body


async def _format_items(data: dict[str, Any], include_content_max: int = 0) -> str:
    """Build a JSON response: { items: [...], cursor?: string }. Items include content when requested."""
    raw_items = data.get("items") or []
    if not raw_items:
        return json.dumps({"items": [], "message": "No matching mail found."}, separators=(",", ":"))
    to_fetch = min(include_content_max, MAX_INCLUDE_CONTENT) if include_content_max else 0
    bodies: list[str] = [""] * len(raw_items)
    if to_fetch:
        num_fetch = min(to_fetch, len(raw_items))
        tasks = [
            _fetch_mail_body(
                raw_items[i]["list"],
                raw_items[i]["month"],
                raw_items[i]["id"],
            )
            for i in range(num_fetch)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                bodies[i] = f"(Failed to fetch content: {r!s})"
            else:
                bodies[i] = r
    items: list[dict[str, Any]] = []
    for i, m in enumerate(raw_items):
        entry = {
            "list": m.get("list", ""),
            "month": m.get("month", ""),
            "id": m.get("id", ""),
            "date": m.get("date", ""),
            "author": m.get("author", ""),
            "email": m.get("email", ""),
            "subject": m.get("subject", ""),
        }
        if i < len(bodies) and bodies[i]:
            entry["content"] = bodies[i]
        items.append(entry)
    out: dict[str, Any] = {"items": items}
    if data.get("cursor"):
        out["cursor"] = data["cursor"]
    return json.dumps(out, separators=(",", ":"))


@mcp.tool()
async def openjdk_mail_search(
    query: str,
    list_name: str | None = None,
    limit: int = 10,
    order: str = "desc",
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_content_max: int = 0,
) -> str:
    """Search OpenJDK mailing list archives by phrase or term (e.g. SSLSocket, JEP 444, virtual threads).

    Query is tokenized and matched against subject and body. Use when the user wants to find
    discussions about a topic. Optionally restrict to one list (e.g. net-dev, core-libs-dev).
    Set include_content_max to 1–5 to include raw message body for the first N results (avoids
    separate get-content calls); 0 = metadata only.
    """
    params: dict[str, str] = {"q": query, "limit": str(min(100, max(1, limit))), "order": order}
    if cursor:
        params["cursor"] = cursor
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if list_name:
        path = f"/lists/{urllib.parse.quote(list_name)}/mail/search"
    else:
        path = "/mail/search"
    data = await _api_get(path, params)
    return await _format_items(data, include_content_max)


@mcp.tool()
async def openjdk_mail_latest(
    list_name: str | None = None,
    limit: int = 10,
    order: str = "desc",
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_content_max: int = 0,
) -> str:
    """Get latest OpenJDK mailing list messages in date order (optionally for one list).
    Set include_content_max to 1–5 to include raw message body for the first N results; 0 = metadata only.
    """
    params: dict[str, str] = {"limit": str(min(100, max(1, limit))), "order": order}
    if cursor:
        params["cursor"] = cursor
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if list_name:
        path = f"/lists/{urllib.parse.quote(list_name)}/mail"
    else:
        path = "/mail"
    data = await _api_get(path, params)
    return await _format_items(data, include_content_max)


@mcp.tool()
async def openjdk_mail_by_author(
    author: str,
    list_name: str | None = None,
    limit: int = 10,
    order: str = "desc",
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_content_max: int = 0,
) -> str:
    """Get OpenJDK mail by author display name (e.g. Brian Goetz). Matching is normalized.
    Set include_content_max to 1–5 to include raw message body for the first N results; 0 = metadata only.
    """
    params: dict[str, str] = {"author": author, "limit": str(min(100, max(1, limit))), "order": order}
    if cursor:
        params["cursor"] = cursor
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if list_name:
        path = f"/lists/{urllib.parse.quote(list_name)}/mail/byauthor"
    else:
        path = "/mail/byauthor"
    data = await _api_get(path, params)
    return await _format_items(data, include_content_max)


@mcp.tool()
async def openjdk_mail_by_email(
    email: str,
    list_name: str | None = None,
    limit: int = 10,
    order: str = "desc",
    cursor: str | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
    include_content_max: int = 0,
) -> str:
    """Get OpenJDK mail by author email address. Matching is normalized.
    Set include_content_max to 1–5 to include raw message body for the first N results; 0 = metadata only.
    """
    params: dict[str, str] = {"email": email, "limit": str(min(100, max(1, limit))), "order": order}
    if cursor:
        params["cursor"] = cursor
    if from_date:
        params["from"] = from_date
    if to_date:
        params["to"] = to_date
    if list_name:
        path = f"/lists/{urllib.parse.quote(list_name)}/mail/byemail"
    else:
        path = "/mail/byemail"
    data = await _api_get(path, params)
    return await _format_items(data, include_content_max)


@mcp.tool()
async def openjdk_mail_status() -> str:
    """Get OpenJDK mail index status (last check and last update timestamps). Returns JSON."""
    data = await _api_get("/mail/status")
    last_check = data.get("last_check") or "unknown"
    last_update = data.get("last_update") or "unknown"
    return json.dumps({"last_check": last_check, "last_update": last_update}, separators=(",", ":"))


@mcp.tool()
async def openjdk_mail_get_content(
    list_name: str, month: str, message_ids: list[str]
) -> str:
    """Get the raw text body of OpenJDK mailing list message(s) from mail.openjdk.org.
    Returns JSON: { "items": [ {"id": "...", "content": "..." }, ... ] }.
    At most 5 IDs are fetched (same cap as include_content_max in search/latest tools).

    The search/latest/by-author/by-email tools return only metadata (list, month, id, date,
    author, email, subject). Use this tool when you need the full message content.
    Parameters must match messages from the API (e.g. list_name='net-dev', month='2025-February', message_ids=['025752','025753']).
    """
    ids = message_ids[:MAX_INCLUDE_CONTENT]
    if not ids:
        return json.dumps({"items": [], "message": "No message IDs provided."}, separators=(",", ":"))
    tasks = [_fetch_mail_body(list_name, month, mid) for mid in ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items: list[dict[str, Any]] = []
    for i, r in enumerate(results):
        content = f"(Failed to fetch content: {r!s})" if isinstance(r, Exception) else r
        items.append({"id": ids[i], "content": content})
    return json.dumps({"items": items}, separators=(",", ":"))


def main() -> None:
    """Entry point for the openjdk-mcp console script."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
