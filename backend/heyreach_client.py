"""Async HTTP client for the HeyReach API (LinkedIn automation).

Base URL: https://api.heyreach.io/api/public
Auth: X-API-KEY header
Rate limit: 300 req/min
"""

import logging
from typing import Any, Dict, List, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.heyreach.io/api/public"


def _headers() -> Dict[str, str]:
    return {
        "X-API-KEY": settings.heyreach_api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


# ---------------------------------------------------------------------------
# Auth check
# ---------------------------------------------------------------------------

async def check_api_key() -> bool:
    """Verify the HeyReach API key is valid."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{BASE_URL}/auth/CheckApiKey",
            headers=_headers(),
        )
        return response.status_code == 200


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------

async def list_campaigns(offset: int = 0, limit: int = 100) -> Dict[str, Any]:
    """Fetch all campaigns from HeyReach.

    POST /campaign/GetAll
    Returns: { "items": [...], "totalCount": N }
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/campaign/GetAll",
            headers=_headers(),
            json={"offset": offset, "limit": limit},
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Stats / Analytics
# ---------------------------------------------------------------------------

async def get_overall_stats(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    campaign_ids: Optional[List[str]] = None,
    account_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Fetch aggregate LinkedIn campaign statistics.

    POST /stats/GetOverallStats
    accountIds and campaignIds are REQUIRED by the API (pass empty list for all).
    Response: { "byDayStats": { "2026-03-14T00:00:00Z": { profileViews, messagesSent,
      totalMessageStarted, totalMessageReplies, inmailMessagesSent, totalInmailStarted,
      totalInmailReplies, connectionsSent, connectionsAccepted,
      messageReplyRate, inMailReplyRate, connectionAcceptanceRate }, ... } }
    """
    body: Dict[str, Any] = {
        # API requires these fields even if empty (means "all accounts / all campaigns")
        "accountIds": account_ids if account_ids is not None else [],
        "campaignIds": campaign_ids if campaign_ids is not None else [],
    }
    if start_date:
        body["startDate"] = start_date
    if end_date:
        body["endDate"] = end_date

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/stats/GetOverallStats",
            headers=_headers(),
            json=body,
        )
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Conversations / Inbox
# ---------------------------------------------------------------------------

async def get_conversations(
    campaign_ids: Optional[List[str]] = None,
    account_ids: Optional[List[str]] = None,
    search: Optional[str] = None,
    seen: Optional[bool] = None,
    offset: int = 0,
    limit: int = 50,
) -> Dict[str, Any]:
    """Fetch LinkedIn conversations from HeyReach inbox.

    POST /inbox/GetConversationsV2
    Returns: { "items": [...], "totalCount": N }
    """
    body: Dict[str, Any] = {"offset": offset, "limit": limit}
    if campaign_ids:
        body["campaignIds"] = campaign_ids
    if account_ids:
        body["accountIds"] = account_ids
    if search:
        body["searchText"] = search
    if seen is not None:
        body["seen"] = seen

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{BASE_URL}/inbox/GetConversationsV2",
            headers=_headers(),
            json=body,
        )
        response.raise_for_status()
        return response.json()


async def get_conversation(
    account_id: str,
    conversation_id: str,
) -> Dict[str, Any]:
    """Fetch the full message thread for a single conversation.

    GET /inbox/GetChatroom/{accountId}/{conversationId}
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        response = await client.get(
            f"{BASE_URL}/inbox/GetChatroom/{account_id}/{conversation_id}",
            headers=_headers(),
        )
        response.raise_for_status()
        return response.json()


async def send_message(
    conversation_id: str,
    account_id: str,
    message: str,
) -> Dict[str, Any]:
    """Send a LinkedIn message in an existing conversation.

    POST /inbox/SendMessage
    HeyReach V2 uses linkedInConversationId/linkedInAccountId field names.
    We try V2 first, then fall back to V1 legacy names if that fails.
    """
    # Try multiple payload shapes — HeyReach V2 field names differ from V1
    payload_variants = [
        # V2 shape (matches GetConversationsV2 field names)
        {
            "linkedInConversationId": conversation_id,
            "linkedInAccountId": account_id,
            "text": message,
        },
        {
            "linkedInConversationId": conversation_id,
            "linkedInAccountId": account_id,
            "message": message,
        },
        # V1 legacy shape
        {
            "conversationId": conversation_id,
            "accountId": account_id,
            "message": message,
        },
        # Alternate V1
        {
            "conversationId": conversation_id,
            "accountId": account_id,
            "text": message,
        },
    ]

    last_error_body = ""
    last_status = 0

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, body in enumerate(payload_variants):
            try:
                response = await client.post(
                    f"{BASE_URL}/inbox/SendMessage",
                    headers=_headers(),
                    json=body,
                )
                if response.status_code < 400:
                    logger.info(
                        "HeyReach send_message succeeded with payload variant %d (keys: %s)",
                        i, list(body.keys()),
                    )
                    try:
                        return response.json()
                    except Exception:
                        return {"status": "sent"}
                last_status = response.status_code
                last_error_body = response.text[:500]
                logger.warning(
                    "HeyReach SendMessage variant %d failed: %d — %s",
                    i, response.status_code, last_error_body,
                )
                # Only retry with next variant on 400-level errors (bad field names)
                # For 401/403/5xx there's no point in trying other payloads
                if response.status_code in (401, 403) or response.status_code >= 500:
                    break
            except httpx.HTTPError as exc:
                last_error_body = str(exc)
                logger.warning("HeyReach SendMessage variant %d HTTP error: %s", i, exc)

    raise RuntimeError(
        f"HeyReach SendMessage failed (status {last_status}): {last_error_body}"
    )
