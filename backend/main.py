import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, func, select

from ai_service import classify_reply, generate_draft, generate_followup, revise_draft, classify_linkedin_message, generate_linkedin_draft
from config import settings
from models import AppSettings, Campaign, FollowUp, Reply, LinkedInCampaign, LinkedInConversation
import heyreach_client

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Inbox Manager", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

engine = create_engine(settings.database_url, echo=False)


@app.on_event("startup")
def on_startup():
    SQLModel.metadata.create_all(engine)
    logger.info("Database tables created")


def get_session():
    return Session(engine)


def _plain_text_to_html(text: str) -> str:
    """Convert plain text to HTML with clickable hyperlinks and line breaks.

    Finds all http/https URLs and wraps them in <a> tags so they are
    clickable in the prospect's email client (Instantly replies).
    """
    def _make_link(match: re.Match) -> str:
        url = match.group(1)
        # Strip trailing punctuation that is likely sentence-ending, not part of the URL
        trailing = ""
        while url and url[-1] in ".,;:!?)":
            trailing = url[-1] + trailing
            url = url[:-1]
        return (
            f'<a href="{url}" target="_blank" '
            f'style="color: #3366FF; text-decoration: underline;">'
            f"{url}</a>{trailing}"
        )

    html = re.sub(r"(https?://\S+)", _make_link, text)
    html = html.replace("\n", "<br>")
    return html


# ---------------------------------------------------------------------------
# Settings endpoints
# ---------------------------------------------------------------------------
@app.get("/api/settings")
async def get_settings():
    """Get current app settings."""
    with get_session() as session:
        settings_row = session.get(AppSettings, 1)
        if not settings_row:
            settings_row = AppSettings(id=1, approval_mode="human")
            session.add(settings_row)
            session.commit()
            session.refresh(settings_row)
        return {"approval_mode": settings_row.approval_mode}


class UpdateSettingsRequest(BaseModel):
    approval_mode: str  # "human" or "automated"


@app.put("/api/settings")
async def update_settings(request: UpdateSettingsRequest):
    """Update app settings."""
    if request.approval_mode not in ("human", "automated"):
        raise HTTPException(status_code=400, detail="approval_mode must be 'human' or 'automated'")
    with get_session() as session:
        settings_row = session.get(AppSettings, 1)
        if not settings_row:
            settings_row = AppSettings(id=1, approval_mode=request.approval_mode)
            session.add(settings_row)
        else:
            settings_row.approval_mode = request.approval_mode
            session.add(settings_row)
        session.commit()
        logger.info(f"Approval mode changed to: {request.approval_mode}")
        return {"approval_mode": request.approval_mode}


# ---------------------------------------------------------------------------
# Pydantic schemas for request/response
# ---------------------------------------------------------------------------
class InstantlyWebhookPayload(BaseModel):
    """Payload from Instantly.ai reply_received webhook."""
    event_type: str = "reply_received"
    # These fields come from Instantly webhook - names may vary
    reply_to_uuid: Optional[str] = None
    email_id: Optional[str] = None
    lead_email: Optional[str] = None
    from_email: Optional[str] = None
    campaign_id: Optional[str] = None
    campaign_name: Optional[str] = None
    reply_text: Optional[str] = None
    reply_body: Optional[str] = None
    reply_subject: Optional[str] = None
    timestamp: Optional[str] = None
    # Allow extra fields from webhook
    model_config = {"extra": "allow"}


class SendReplyRequest(BaseModel):
    reply_id: int
    custom_response: Optional[str] = None  # If operator edited the draft
    approved_by: str = "slack_user"


class FeedbackRequest(BaseModel):
    feedback: str


class GenerateFollowUpRequest(BaseModel):
    reply_id: int


class StatsOverviewResponse(BaseModel):
    total: int
    interested: int
    not_interested: int
    ooo: int
    unsubscribe: int
    info_request: int
    wrong_person: int
    dnc: int
    pending_approval: int
    sent: int
    avg_response_time_minutes: Optional[float] = None
    approval_rate: Optional[float] = None


# ---------------------------------------------------------------------------
# Webhook endpoint - receives replies from Instantly.ai
# ---------------------------------------------------------------------------
@app.post("/webhook/instantly")
async def receive_instantly_webhook(payload: InstantlyWebhookPayload):
    """Receive a reply webhook from Instantly.ai, classify it, draft a response,
    and forward to n8n for Slack notification."""

    # Normalize field names (Instantly may use different field names)
    reply_uuid = payload.reply_to_uuid or payload.email_id or ""
    lead_email = payload.lead_email or payload.from_email or ""
    reply_body = payload.reply_text or payload.reply_body or ""
    campaign_id = payload.campaign_id or ""
    campaign_name = payload.campaign_name or ""
    reply_subject = payload.reply_subject or ""

    if not reply_body:
        raise HTTPException(status_code=400, detail="No reply body in webhook payload")

    logger.info(f"Received reply from {lead_email} (campaign: {campaign_name})")

    with get_session() as session:
        # Deduplicate: skip if we already processed this reply
        existing = session.exec(
            select(Reply).where(Reply.instantly_uuid == reply_uuid)
        ).first()
        if existing:
            logger.info(f"Duplicate webhook for {reply_uuid}, skipping")
            return {"status": "duplicate", "reply_id": existing.id}

        # Ensure campaign exists
        campaign = session.get(Campaign, campaign_id)
        if not campaign and campaign_id:
            campaign = Campaign(id=campaign_id, name=campaign_name)
            session.add(campaign)

        # Create reply record
        reply = Reply(
            instantly_uuid=reply_uuid,
            lead_email=lead_email,
            campaign_id=campaign_id,
            campaign_name=campaign_name,
            reply_body=reply_body,
            reply_subject=reply_subject,
            status="pending_classification",
            received_at=datetime.utcnow(),
        )
        session.add(reply)
        session.commit()
        session.refresh(reply)
        reply_id = reply.id

    # Classify the reply with AI
    category = await classify_reply(reply_body)
    logger.info(f"Classified reply {reply_id} as: {category}")

    # Check thread: is the latest message from us? Extract sender name and eaccount.
    human_managed = False
    sender_name = "Unknown"
    eaccount = ""
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{settings.instantly_api_base}/emails",
                headers={"Authorization": f"Bearer {settings.instantly_api_key}"},
                params={"lead": lead_email, "sort_order": "desc", "limit": 10},
                timeout=10.0,
            )
            resp.raise_for_status()
            items = resp.json().get("items", [])
            if items:
                latest = items[0]
                # ue_type 1=campaign sent, 3=manual/unibox sent
                if latest.get("ue_type") in (1, 3):
                    human_managed = True
                    logger.info(f"Reply {reply_id} already handled by human - latest message is from us")

                # Extract sender name and eaccount from our sent messages
                for item in items:
                    if item.get("ue_type") in (1, 3):
                        if not eaccount:
                            eaccount = item.get("eaccount", "") or item.get("from_address_email", "")
                        from_addr = item.get("from_address_email", "")
                        # Try to get name from from_address_json first
                        from_json = item.get("from_address_json", [])
                        if from_json and isinstance(from_json, list) and len(from_json) > 0:
                            name = from_json[0].get("name", "")
                            if name:
                                sender_name = name.split()[0]  # First name only
                                break
                        # Fallback: extract from email body sign-off
                        body_data = item.get("body", {})
                        body_text = ""
                        if isinstance(body_data, dict):
                            body_text = body_data.get("text", "") or body_data.get("html", "")
                        elif isinstance(body_data, str):
                            body_text = body_data
                        # Look for common sign-off patterns (with or without newlines)
                        # Strip HTML tags first for better matching
                        clean_text = re.sub(r'<[^>]+>', '\n', body_text)
                        signoff = re.search(r'(?:Best|Cheers|Thanks|Regards|Kind regards|Warm regards|Best regards)[,\s]*[\n\r]+\s*([A-Z][a-z]+)', clean_text)
                        if signoff:
                            sender_name = signoff.group(1)
                            break
                        # Also try "From: FirstName LastName" pattern in the thread
                        from_header = re.search(r'From:\s*([A-Z][a-z]+)\s+[A-Z][a-z]+\s*<', body_text)
                        if from_header:
                            sender_name = from_header.group(1)
                            break
                        # Try from email address as last resort
                        if from_addr and "@" in from_addr:
                            name_part = from_addr.split("@")[0]
                            # Handle "lewis.j" -> skip, "jessica" -> "Jessica", "grace.smith" -> "Grace"
                            parts = name_part.split(".")
                            # Use the longest part (likely the first name, not initial)
                            best = max(parts, key=len)
                            if len(best) > 1:
                                sender_name = best.title()
                            break
    except Exception as e:
        logger.warning(f"Could not check thread for {reply_id}: {e}")

    # Last resort: try to extract sender name from the prospect's reply body (quoted "From:" header)
    if sender_name == "Unknown" or (sender_name and len(sender_name) <= 2):
        from_match = re.search(r'From:\s*([A-Z][a-z]+)\s+[A-Z][a-z]+\s*<', reply_body)
        if from_match:
            sender_name = from_match.group(1)
    # Also check for sign-off in the reply body's quoted section
    if sender_name == "Unknown" or (sender_name and len(sender_name) <= 2):
        signoff_match = re.search(r'(?:Best|Cheers|Thanks|Regards|Best regards)[,\s]*[\n\r]+\s*([A-Z][a-z]+)', reply_body)
        if signoff_match:
            sender_name = signoff_match.group(1)

    logger.info(f"Reply {reply_id}: sender_name={sender_name}, human_managed={human_managed}")

    # Generate draft response for actionable categories (skip if human already replied)
    draft = ""
    if not human_managed and category in ("interested", "info_request"):
        draft = await generate_draft(reply_body, lead_email, campaign_name, category, sender_name=sender_name)

    # Check approval mode
    with get_session() as session:
        settings_row = session.get(AppSettings, 1)
        approval_mode = settings_row.approval_mode if settings_row else "human"

    # Update reply record
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        reply.category = category
        reply.draft_response = draft
        reply.eaccount = eaccount

        # Check if draft needs Josh's help - never auto-send these
        needs_josh = draft and "needs josh" in draft.lower()

        if human_managed:
            reply.status = "human_managed"
        elif category in ("ooo", "unsubscribe", "dnc", "wrong_person", "not_interested"):
            reply.status = "auto_handled"
        elif needs_josh:
            # Never auto-send, always needs manual intervention
            reply.status = "needs_josh"
        elif approval_mode == "automated" and draft:
            # Auto-send: send via Instantly immediately
            reply.status = "sent"
            reply.approved_at = datetime.utcnow()
            reply.sent_at = datetime.utcnow()
            reply.approved_by = "auto"
        else:
            reply.status = "pending_approval"

        session.add(reply)
        session.commit()
        session.refresh(reply)

        # If automated mode and actionable, send via Instantly
        if reply.status == "sent" and approval_mode == "automated":
            try:
                async with httpx.AsyncClient() as http_client:
                    resp = await http_client.post(
                        f"{settings.instantly_api_base}/emails/reply",
                        headers={
                            "Authorization": f"Bearer {settings.instantly_api_key}",
                            "Content-Type": "application/json",
                        },
                        json={
                            "reply_to_uuid": reply.instantly_uuid,
                            "eaccount": reply.eaccount,
                            "subject": f"Re: {reply.reply_subject}" if reply.reply_subject else "Re:",
                            "body": {
                                "html": _plain_text_to_html(reply.draft_response),
                                "text": reply.draft_response,
                            },
                        },
                        timeout=15.0,
                    )
                    resp.raise_for_status()
                logger.info(f"Auto-sent reply {reply_id} via Instantly")
                _schedule_followups(session, reply)
            except Exception as e:
                logger.error(f"Auto-send failed for {reply_id}: {e}")
                reply.status = "pending_approval"
                reply.sent_at = None
                reply.approved_at = None
                reply.approved_by = ""
                session.add(reply)
                session.commit()
                session.refresh(reply)

        # Prepare data for n8n
        n8n_payload = {
            "reply_id": reply.id,
            "lead_email": reply.lead_email,
            "campaign_name": reply.campaign_name,
            "category": reply.category,
            "reply_body": reply.reply_body,
            "reply_subject": reply.reply_subject,
            "draft_response": reply.draft_response,
            "status": reply.status,
            "received_at": reply.received_at.isoformat() + "Z",
        }

    # Forward to n8n for Slack notification
    try:
        async with httpx.AsyncClient() as http_client:
            await http_client.post(
                settings.n8n_slack_webhook_url,
                json=n8n_payload,
                timeout=10.0,
            )
        logger.info(f"Forwarded reply {reply_id} to n8n")
    except Exception as e:
        logger.error(f"Failed to forward to n8n: {e}")

    return {"status": "processed", "reply_id": reply_id, "category": category}


# ---------------------------------------------------------------------------
# Send reply via Instantly.ai
# ---------------------------------------------------------------------------
@app.post("/api/send-reply")
async def send_reply(request: SendReplyRequest):
    """Send an approved reply through Instantly.ai API."""
    with get_session() as session:
        reply = session.get(Reply, request.reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")

        response_body = request.custom_response or reply.draft_response
        if not response_body:
            raise HTTPException(status_code=400, detail="No response body to send")
        if "needs josh" in response_body.lower():
            raise HTTPException(status_code=400, detail="This reply needs Josh's help. Cannot auto-send.")

        # Send via Instantly.ai API v2
        try:
            async with httpx.AsyncClient() as http_client:
                resp = await http_client.post(
                    f"{settings.instantly_api_base}/emails/reply",
                    headers={
                        "Authorization": f"Bearer {settings.instantly_api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "reply_to_uuid": reply.instantly_uuid,
                        "eaccount": reply.eaccount,
                        "subject": f"Re: {reply.reply_subject}" if reply.reply_subject else "Re:",
                        "body": {
                            "html": _plain_text_to_html(response_body),
                            "text": response_body,
                        },
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            logger.error(f"Instantly API error: {e.response.text}")
            raise HTTPException(
                status_code=502,
                detail=f"Instantly API error: {e.response.status_code}",
            )
        except Exception as e:
            logger.error(f"Failed to send reply via Instantly: {e}")
            raise HTTPException(status_code=502, detail="Failed to send reply")

        # Update status
        reply.status = "sent"
        reply.approved_at = datetime.utcnow()
        reply.sent_at = datetime.utcnow()
        reply.approved_by = request.approved_by
        if request.custom_response:
            reply.draft_response = request.custom_response
        session.add(reply)
        session.commit()

        logger.info(f"Reply {request.reply_id} sent via Instantly")

        # Schedule follow-ups
        _schedule_followups(session, reply)

        return {
            "status": "sent",
            "reply_id": reply.id,
            "lead_email": reply.lead_email,
        }


def _schedule_followups(session: Session, reply: Reply):
    """Create follow-up records. Follow-up 1 at 2h, then every 24h up to 9 total."""
    cumulative_hours = 0
    for i, hours in enumerate(settings.followup_windows_hours, start=1):
        cumulative_hours += hours
        followup = FollowUp(
            reply_id=reply.id,
            sequence_num=i,
            scheduled_for=datetime.utcnow() + timedelta(hours=cumulative_hours),
        )
        session.add(followup)
    session.commit()


# ---------------------------------------------------------------------------
# Follow-up endpoints (called by n8n cron)
# ---------------------------------------------------------------------------
@app.get("/api/pending-followups")
async def get_pending_followups():
    """Get follow-ups that are due and haven't been sent."""
    now = datetime.utcnow()
    with get_session() as session:
        followups = session.exec(
            select(FollowUp)
            .where(FollowUp.status == "pending")
            .where(FollowUp.scheduled_for <= now)
        ).all()

        results = []
        for fu in followups:
            reply = session.get(Reply, fu.reply_id)
            # Only follow up if the original reply was sent and no new reply came in
            valid_statuses = ("sent",) + tuple(f"follow_up_{i}" for i in range(1, 9))
            if reply and reply.status in valid_statuses:
                results.append({
                    "followup_id": fu.id,
                    "reply_id": fu.reply_id,
                    "sequence_num": fu.sequence_num,
                    "lead_email": reply.lead_email,
                    "campaign_name": reply.campaign_name,
                    "original_reply": reply.reply_body,
                    "last_response": reply.draft_response,
                    "days_since": (now - (reply.sent_at or reply.received_at)).days,
                    "scheduled_for": fu.scheduled_for.isoformat() + "Z",
                })

    return {"followups": results, "count": len(results)}


@app.post("/api/generate-followup")
async def generate_followup_endpoint(request: GenerateFollowUpRequest):
    """Generate a follow-up message for a specific reply."""
    with get_session() as session:
        reply = session.get(Reply, request.reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")

        # Find the next pending follow-up
        followup = session.exec(
            select(FollowUp)
            .where(FollowUp.reply_id == request.reply_id)
            .where(FollowUp.status == "pending")
            .order_by(FollowUp.sequence_num)
        ).first()

        if not followup:
            return {"status": "no_pending_followups"}

        now = datetime.utcnow()
        hours_since = int((now - (reply.sent_at or reply.received_at)).total_seconds() / 3600)
        days_since = hours_since // 24
        hour_window = settings.followup_windows_hours[followup.sequence_num - 1] if followup.sequence_num <= len(settings.followup_windows_hours) else 24
        day_window = hour_window // 24 if hour_window >= 24 else 0

        body = await generate_followup(
            lead_email=reply.lead_email,
            campaign_name=reply.campaign_name,
            original_reply=reply.reply_body,
            last_response=reply.draft_response,
            sequence_num=followup.sequence_num,
            day_window=day_window,
            days_since=days_since,
        )

        followup.follow_up_body = body
        session.add(followup)
        session.commit()

        return {
            "followup_id": followup.id,
            "reply_id": reply.id,
            "sequence_num": followup.sequence_num,
            "lead_email": reply.lead_email,
            "campaign_name": reply.campaign_name,
            "follow_up_body": body,
            "day_window": day_window,
        }


# ---------------------------------------------------------------------------
# Approve & send reply from dashboard
# ---------------------------------------------------------------------------
@app.post("/api/replies/{reply_id}/approve")
async def approve_reply_from_dashboard(reply_id: int):
    """Approve and send a reply from the dashboard (same as Slack approval)."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")
        if reply.status == "sent":
            raise HTTPException(status_code=400, detail="Reply already sent")
        if not reply.draft_response:
            raise HTTPException(status_code=400, detail="No draft response to send")
        if "needs josh" in reply.draft_response.lower():
            raise HTTPException(status_code=400, detail="This reply needs Josh's help. Cannot auto-send.")

        # Fetch eaccount from Instantly if missing (for older replies)
        if not reply.eaccount:
            try:
                async with httpx.AsyncClient() as http_client:
                    thread_resp = await http_client.get(
                        f"{settings.instantly_api_base}/emails",
                        headers={"Authorization": f"Bearer {settings.instantly_api_key}"},
                        params={"lead": reply.lead_email, "sort_order": "desc", "limit": 5},
                        timeout=10.0,
                    )
                    thread_resp.raise_for_status()
                    for item in thread_resp.json().get("items", []):
                        if item.get("ue_type") in (1, 3):
                            reply.eaccount = item.get("eaccount", "") or item.get("from_address_email", "")
                            if reply.eaccount:
                                session.add(reply)
                                session.commit()
                                session.refresh(reply)
                                logger.info(f"Fetched eaccount for reply {reply_id}: {reply.eaccount}")
                                break
            except Exception as e:
                logger.warning(f"Could not fetch eaccount for reply {reply_id}: {e}")

        if not reply.eaccount:
            raise HTTPException(status_code=400, detail="Cannot determine sending email account. Check Instantly thread.")

        # Send via Instantly.ai API v2
        instantly_sent = False
        try:
            async with httpx.AsyncClient() as http_client:
                send_payload = {
                    "reply_to_uuid": reply.instantly_uuid,
                    "eaccount": reply.eaccount,
                    "subject": f"Re: {reply.reply_subject}" if reply.reply_subject else "Re:",
                    "body": {
                        "html": _plain_text_to_html(reply.draft_response),
                        "text": reply.draft_response,
                    },
                }
                logger.info(f"Sending reply {reply_id} via Instantly: eaccount={reply.eaccount}, uuid={reply.instantly_uuid}")
                resp = await http_client.post(
                    f"{settings.instantly_api_base}/emails/reply",
                    headers={
                        "Authorization": f"Bearer {settings.instantly_api_key}",
                        "Content-Type": "application/json",
                    },
                    json=send_payload,
                    timeout=15.0,
                )
                resp.raise_for_status()
                instantly_sent = True
                logger.info(f"Reply {reply_id} sent successfully via Instantly")
        except Exception as e:
            logger.error(f"Instantly API send failed for reply {reply_id}: {e}")
            raise HTTPException(status_code=502, detail=f"Failed to send via Instantly: {str(e)}")

        # Update status only after successful send
        reply.status = "sent"
        reply.approved_at = datetime.utcnow()
        reply.sent_at = datetime.utcnow()
        reply.approved_by = "dashboard"
        session.add(reply)
        session.commit()
        session.refresh(reply)

        logger.info(f"Reply {reply_id} approved & sent from dashboard")

        # Schedule follow-ups
        _schedule_followups(session, reply)

        # Notify Slack about the approval
        try:
            async with httpx.AsyncClient() as http_client:
                await http_client.post(
                    settings.n8n_slack_webhook_url,
                    json={
                        "reply_id": reply.id,
                        "lead_email": reply.lead_email,
                        "campaign_name": reply.campaign_name,
                        "category": reply.category,
                        "reply_body": reply.reply_body,
                        "draft_response": reply.draft_response,
                        "status": "sent",
                        "approved_by": "dashboard",
                        "received_at": reply.received_at.isoformat() + "Z",
                    },
                    timeout=10.0,
                )
        except Exception as e:
            logger.error(f"Failed to notify Slack: {e}")

        return {
            "status": "sent",
            "reply_id": reply.id,
            "lead_email": reply.lead_email,
            "sent_at": reply.sent_at.isoformat() + "Z",
            "instantly_sent": instantly_sent,
        }


# ---------------------------------------------------------------------------
# Reject reply from dashboard
# ---------------------------------------------------------------------------
@app.post("/api/replies/{reply_id}/reject")
async def reject_reply_from_dashboard(reply_id: int):
    """Reject a reply from the dashboard."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")
        if reply.status == "sent":
            raise HTTPException(status_code=400, detail="Reply already sent")

        reply.status = "rejected"
        session.add(reply)
        session.commit()

        logger.info(f"Reply {reply_id} rejected from dashboard")
        return {"status": "rejected", "reply_id": reply.id}


# ---------------------------------------------------------------------------
# Feedback on AI draft (called from dashboard)
# ---------------------------------------------------------------------------
@app.post("/api/replies/{reply_id}/feedback")
async def submit_feedback(reply_id: int, request: FeedbackRequest):
    """Revise the AI draft based on user feedback."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")

        revised = await revise_draft(
            reply_body=reply.reply_body,
            lead_email=reply.lead_email,
            campaign_name=reply.campaign_name,
            category=reply.category,
            current_draft=reply.draft_response,
            feedback=request.feedback,
        )

        reply.draft_response = revised
        session.add(reply)
        session.commit()

        return {
            "reply_id": reply_id,
            "draft_response": revised,
            "status": "revised",
        }


# ---------------------------------------------------------------------------
# Get single reply with full text
# ---------------------------------------------------------------------------
@app.get("/api/replies/{reply_id}")
async def get_reply(reply_id: int):
    """Get a single reply with full text (not truncated)."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")
        return {
            "id": reply.id,
            "lead_email": reply.lead_email,
            "campaign_name": reply.campaign_name,
            "category": reply.category,
            "status": reply.status,
            "reply_body": reply.reply_body,
            "draft_response": reply.draft_response,
            "received_at": reply.received_at.isoformat() + "Z",
            "sent_at": (reply.sent_at.isoformat() + "Z") if reply.sent_at else None,
        }


# ---------------------------------------------------------------------------
# Dashboard API endpoints
# ---------------------------------------------------------------------------
@app.get("/api/stats/overview")
async def stats_overview(
    period: str = Query("all", description="all|today|week|month"),
):
    """Get overview stats for the dashboard."""
    with get_session() as session:
        query = select(Reply)

        # Apply time filter
        now = datetime.utcnow()
        if period == "today":
            query = query.where(Reply.received_at >= now.replace(hour=0, minute=0, second=0))
        elif period == "week":
            query = query.where(Reply.received_at >= now - timedelta(days=7))
        elif period == "month":
            query = query.where(Reply.received_at >= now - timedelta(days=30))

        replies = session.exec(query).all()
        total = len(replies)

        categories = {}
        for cat in ["interested", "not_interested", "ooo", "unsubscribe", "info_request", "wrong_person", "dnc"]:
            categories[cat] = sum(1 for r in replies if r.category == cat)

        pending = sum(1 for r in replies if r.status == "pending_approval")
        sent = sum(1 for r in replies if r.status == "sent")

        # Avg response time (received -> sent)
        response_times = []
        for r in replies:
            if r.sent_at and r.received_at:
                delta = (r.sent_at - r.received_at).total_seconds() / 60
                response_times.append(delta)
        avg_response_time = sum(response_times) / len(response_times) if response_times else None

        # Approval rate
        actionable = sum(1 for r in replies if r.category in ("interested", "info_request", "not_interested"))
        approved = sum(1 for r in replies if r.status in ("approved", "sent") and r.category in ("interested", "info_request", "not_interested"))
        approval_rate = (approved / actionable * 100) if actionable > 0 else None

        return StatsOverviewResponse(
            total=total,
            interested=categories.get("interested", 0),
            not_interested=categories.get("not_interested", 0),
            ooo=categories.get("ooo", 0),
            unsubscribe=categories.get("unsubscribe", 0),
            info_request=categories.get("info_request", 0),
            wrong_person=categories.get("wrong_person", 0),
            dnc=categories.get("dnc", 0),
            pending_approval=pending,
            sent=sent,
            avg_response_time_minutes=avg_response_time,
            approval_rate=approval_rate,
        )


@app.get("/api/stats/campaigns")
async def stats_campaigns(
    period: str = Query("all", description="all|today|week|month"),
):
    """Get per-campaign breakdown."""
    with get_session() as session:
        query = select(Reply)

        now = datetime.utcnow()
        if period == "today":
            query = query.where(Reply.received_at >= now.replace(hour=0, minute=0, second=0))
        elif period == "week":
            query = query.where(Reply.received_at >= now - timedelta(days=7))
        elif period == "month":
            query = query.where(Reply.received_at >= now - timedelta(days=30))

        replies = session.exec(query).all()

        campaigns = {}
        for r in replies:
            key = r.campaign_name or r.campaign_id
            if key not in campaigns:
                campaigns[key] = {
                    "campaign_id": r.campaign_id,
                    "campaign_name": r.campaign_name,
                    "total": 0,
                    "interested": 0,
                    "not_interested": 0,
                    "ooo": 0,
                    "unsubscribe": 0,
                    "info_request": 0,
                    "wrong_person": 0,
                    "dnc": 0,
                    "interest_rate": 0,
                }
            campaigns[key]["total"] += 1
            if r.category in campaigns[key]:
                campaigns[key][r.category] += 1

        # Calculate interest rates
        for c in campaigns.values():
            if c["total"] > 0:
                c["interest_rate"] = round(c["interested"] / c["total"] * 100, 1)

        # Sort by total replies descending
        result = sorted(campaigns.values(), key=lambda x: x["total"], reverse=True)
        return {"campaigns": result}


@app.get("/api/stats/timeline")
async def stats_timeline(
    days: int = Query(30, description="Number of days to look back"),
):
    """Get daily reply counts for timeline chart."""
    with get_session() as session:
        cutoff = datetime.utcnow() - timedelta(days=days)
        replies = session.exec(
            select(Reply).where(Reply.received_at >= cutoff)
        ).all()

        # Group by date
        daily = {}
        for r in replies:
            date_key = r.received_at.strftime("%Y-%m-%d")
            if date_key not in daily:
                daily[date_key] = {
                    "date": date_key,
                    "total": 0,
                    "interested": 0,
                    "not_interested": 0,
                    "ooo": 0,
                    "unsubscribe": 0,
                    "info_request": 0,
                }
            daily[date_key]["total"] += 1
            if r.category in daily[date_key]:
                daily[date_key][r.category] += 1

        # Fill in missing dates
        result = []
        for i in range(days):
            date_key = (datetime.utcnow() - timedelta(days=days - 1 - i)).strftime("%Y-%m-%d")
            if date_key in daily:
                result.append(daily[date_key])
            else:
                result.append({
                    "date": date_key,
                    "total": 0,
                    "interested": 0,
                    "not_interested": 0,
                    "ooo": 0,
                    "unsubscribe": 0,
                    "info_request": 0,
                })

        return {"timeline": result}


@app.get("/api/stats/response-times")
async def stats_response_times():
    """Get response time analytics."""
    with get_session() as session:
        replies = session.exec(
            select(Reply).where(Reply.sent_at.isnot(None))
        ).all()

        approval_times = []
        send_times = []
        for r in replies:
            if r.approved_at and r.received_at:
                approval_times.append(
                    (r.approved_at - r.received_at).total_seconds() / 60
                )
            if r.sent_at and r.received_at:
                send_times.append(
                    (r.sent_at - r.received_at).total_seconds() / 60
                )

        return {
            "avg_approval_time_minutes": (
                round(sum(approval_times) / len(approval_times), 1)
                if approval_times
                else None
            ),
            "avg_send_time_minutes": (
                round(sum(send_times) / len(send_times), 1)
                if send_times
                else None
            ),
            "total_sent": len(replies),
        }


@app.get("/api/stats/followups")
async def stats_followups():
    """Get follow-up effectiveness stats."""
    with get_session() as session:
        followups = session.exec(select(FollowUp)).all()

        total = len(followups)
        sent = sum(1 for f in followups if f.status == "sent")
        pending = sum(1 for f in followups if f.status == "pending")

        by_sequence = {}
        for seq in range(1, 10):
            seq_followups = [f for f in followups if f.sequence_num == seq]
            seq_sent = sum(1 for f in seq_followups if f.status == "sent")
            by_sequence[f"followup_{seq}"] = {
                "total": len(seq_followups),
                "sent": seq_sent,
            }

        return {
            "total": total,
            "sent": sent,
            "pending": pending,
            "by_sequence": by_sequence,
        }


@app.get("/api/replies")
async def list_replies(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    category: Optional[str] = None,
    campaign_id: Optional[str] = None,
    status: Optional[str] = None,
):
    """Get paginated list of all replies with filters."""
    with get_session() as session:
        query = select(Reply)

        if category:
            query = query.where(Reply.category == category)
        if campaign_id:
            query = query.where(Reply.campaign_id == campaign_id)
        if status:
            query = query.where(Reply.status == status)

        query = query.order_by(Reply.received_at.desc())

        # Count total
        count_query = select(func.count()).select_from(Reply)
        if category:
            count_query = count_query.where(Reply.category == category)
        if campaign_id:
            count_query = count_query.where(Reply.campaign_id == campaign_id)
        if status:
            count_query = count_query.where(Reply.status == status)
        total = session.exec(count_query).one()

        # Paginate
        replies = session.exec(
            query.offset((page - 1) * per_page).limit(per_page)
        ).all()

        return {
            "replies": [
                {
                    "id": r.id,
                    "lead_email": r.lead_email,
                    "campaign_name": r.campaign_name,
                    "category": r.category,
                    "status": r.status,
                    "reply_body": r.reply_body,
                    "draft_response": r.draft_response or "",
                    "received_at": r.received_at.isoformat() + "Z",
                    "sent_at": (r.sent_at.isoformat() + "Z") if r.sent_at else None,
                }
                for r in replies
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }


# ---------------------------------------------------------------------------
# Fetch full conversation thread from Instantly.ai
# ---------------------------------------------------------------------------
@app.get("/api/replies/{reply_id}/thread")
async def get_reply_thread(reply_id: int):
    """Fetch the full email conversation thread from Instantly.ai."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")

    # Fetch thread from Instantly using lead email
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{settings.instantly_api_base}/emails",
                headers={
                    "Authorization": f"Bearer {settings.instantly_api_key}",
                },
                params={
                    "lead": reply.lead_email,
                    "sort_order": "asc",
                    "limit": 50,
                },
                timeout=15.0,
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        logger.error(f"Failed to fetch thread from Instantly: {e}")
        raise HTTPException(status_code=502, detail="Failed to fetch conversation from Instantly")

    # Format the thread
    thread = []
    for email in data.get("items", []):
        body_text = ""
        body_data = email.get("body", {})
        if isinstance(body_data, dict):
            body_text = body_data.get("text", "") or body_data.get("html", "")
        elif isinstance(body_data, str):
            body_text = body_data

        thread.append({
            "id": email.get("id", ""),
            "from": email.get("from_address_email", ""),
            "to": email.get("to_address_email_list", ""),
            "subject": email.get("subject", ""),
            "body": body_text,
            "timestamp": email.get("timestamp_email", email.get("timestamp_created", "")),
            "type": "sent" if email.get("ue_type") in (1, 3) else "received",
            "content_preview": email.get("content_preview", ""),
        })

    return {
        "reply_id": reply_id,
        "lead_email": reply.lead_email,
        "campaign_name": reply.campaign_name,
        "thread": thread,
        "count": len(thread),
    }


# ---------------------------------------------------------------------------
# Update reply status (called by n8n on reject)
# ---------------------------------------------------------------------------
@app.patch("/api/replies/{reply_id}")
async def update_reply(reply_id: int, status: str = Query(...)):
    """Update a reply's status (e.g., reject from Slack)."""
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        if not reply:
            raise HTTPException(status_code=404, detail="Reply not found")
        reply.status = status
        session.add(reply)
        session.commit()
        return {"status": "updated", "reply_id": reply_id, "new_status": status}


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/health")
async def health():
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat() + "Z"}


# ===========================================================================
# LinkedIn / HeyReach routes
# ===========================================================================

LINKEDIN_STATUS_MAP = {
    "IN_PROGRESS": "active",
    "PAUSED": "paused",
    "FINISHED": "finished",
    "DRAFT": "draft",
    "STOPPED": "stopped",
}

LINKEDIN_CATEGORIES_LIST = [
    "interested",
    "not_interested",
    "info_request",
    "referral",
    "wrong_person",
    "out_of_office",
    "already_client",
]


# ---------------------------------------------------------------------------
# LinkedIn Campaigns
# ---------------------------------------------------------------------------

@app.get("/api/linkedin/campaigns")
async def list_linkedin_campaigns():
    """Return all LinkedIn campaigns stored in the local database."""
    with get_session() as session:
        campaigns = list(
            session.exec(
                select(LinkedInCampaign).order_by(LinkedInCampaign.created_at.desc())
            ).all()
        )
        return {
            "campaigns": [
                {
                    "id": c.id,
                    "heyreach_campaign_id": c.heyreach_campaign_id,
                    "name": c.name,
                    "status": c.status,
                    "created_at": c.created_at.isoformat() + "Z",
                    "updated_at": c.updated_at.isoformat() + "Z",
                }
                for c in campaigns
            ],
            "total": len(campaigns),
        }


@app.post("/api/linkedin/campaigns/sync")
async def sync_linkedin_campaigns():
    """Fetch all campaigns from HeyReach and upsert into local DB."""
    created = 0
    updated = 0
    offset = 0
    limit = 100

    try:
        while True:
            data = await heyreach_client.list_campaigns(offset=offset, limit=limit)
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break

            with get_session() as session:
                for item in items:
                    raw_id = item.get("id")
                    if not raw_id:
                        continue
                    camp_id = str(raw_id)

                    existing = session.exec(
                        select(LinkedInCampaign).where(
                            LinkedInCampaign.heyreach_campaign_id == camp_id
                        )
                    ).first()

                    camp_name = item.get("name", "") or ""
                    raw_status = item.get("status", "")
                    camp_status = LINKEDIN_STATUS_MAP.get(raw_status, raw_status.lower() if raw_status else "unknown")

                    if existing:
                        existing.name = camp_name or existing.name
                        existing.status = camp_status
                        existing.updated_at = datetime.utcnow()
                        session.add(existing)
                        updated += 1
                    else:
                        campaign = LinkedInCampaign(
                            heyreach_campaign_id=camp_id,
                            name=camp_name,
                            status=camp_status,
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                        )
                        session.add(campaign)
                        created += 1
                session.commit()

            total_count = data.get("totalCount", 0)
            offset += limit
            if offset >= total_count:
                break

    except Exception as exc:
        logger.exception("Error syncing LinkedIn campaigns from HeyReach")
        raise HTTPException(status_code=502, detail=f"HeyReach API error: {exc}")

    logger.info("LinkedIn campaign sync: %d created, %d updated", created, updated)
    return {"status": "synced", "created": created, "updated": updated}


# ---------------------------------------------------------------------------
# LinkedIn Conversations (inbox)
# ---------------------------------------------------------------------------

@app.post("/api/linkedin/conversations/sync")
async def sync_linkedin_conversations(max_conversations: int = Query(50, le=1000)):
    """Fetch the most recent conversations from HeyReach and store them.

    Capped at max_conversations (default 200) to keep sync fast.
    Classification and draft generation happen lazily when a conversation is opened.
    """
    synced = 0
    skipped = 0
    offset = 0
    limit = 50

    try:
        while synced + skipped < max_conversations:
            data = await heyreach_client.get_conversations(offset=offset, limit=limit)
            items = data.get("items", []) if isinstance(data, dict) else []
            if not items:
                break

            with get_session() as session:
                for item in items:
                    conv_id = str(item.get("conversationId", ""))
                    if not conv_id:
                        continue

                    existing = session.exec(
                        select(LinkedInConversation).where(
                            LinkedInConversation.heyreach_conversation_id == conv_id
                        )
                    ).first()
                    if existing:
                        skipped += 1
                        continue  # Already stored

                    account_id = str(item.get("accountId", ""))
                    heyreach_camp_id = str(item.get("campaignId", ""))
                    last_message = item.get("lastMessage", "") or ""
                    lead_name = item.get("leadName", "") or ""
                    lead_url = item.get("leadLinkedInUrl", "") or ""
                    lead_title = item.get("leadTitle", "") or ""
                    lead_company = item.get("leadCompany", "") or ""

                    # Look up local campaign
                    local_campaign = session.exec(
                        select(LinkedInCampaign).where(
                            LinkedInCampaign.heyreach_campaign_id == heyreach_camp_id
                        )
                    ).first()

                    # Store with pending_classification — AI runs when conversation is opened
                    conv = LinkedInConversation(
                        heyreach_conversation_id=conv_id,
                        account_id=account_id,
                        campaign_id=local_campaign.id if local_campaign else None,
                        heyreach_campaign_id=heyreach_camp_id,
                        lead_name=lead_name,
                        lead_linkedin_url=lead_url,
                        lead_title=lead_title,
                        lead_company=lead_company,
                        last_message=last_message,
                        category="",
                        draft_response="",
                        status="pending_classification",
                        created_at=datetime.utcnow(),
                    )
                    session.add(conv)
                    synced += 1

                session.commit()

            offset += limit

    except Exception as exc:
        logger.exception("Error syncing LinkedIn conversations")
        raise HTTPException(status_code=502, detail=f"HeyReach sync error: {exc}")

    logger.info("LinkedIn conversation sync: %d new, %d already existed", synced, skipped)
    return {"status": "synced", "count": synced, "skipped": skipped}


@app.get("/api/linkedin/conversations")
async def list_linkedin_conversations(
    page: int = Query(1, ge=1),
    category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    per_page: int = Query(50, le=100),
):
    """List LinkedIn conversations from local DB with pagination."""
    with get_session() as session:
        query = select(LinkedInConversation)
        if category:
            query = query.where(LinkedInConversation.category == category)
        if status:
            query = query.where(LinkedInConversation.status == status)
        query = query.order_by(LinkedInConversation.created_at.desc())

        all_convs = list(session.exec(query).all())
        total = len(all_convs)
        pages = max(1, (total + per_page - 1) // per_page)
        offset_val = (page - 1) * per_page
        page_convs = all_convs[offset_val: offset_val + per_page]

        return {
            "conversations": [
                {
                    "id": c.id,
                    "heyreach_conversation_id": c.heyreach_conversation_id,
                    "account_id": c.account_id,
                    "lead_name": c.lead_name,
                    "lead_linkedin_url": c.lead_linkedin_url,
                    "lead_title": c.lead_title,
                    "lead_company": c.lead_company,
                    "last_message": c.last_message,
                    "category": c.category,
                    "draft_response": c.draft_response,
                    "status": c.status,
                    "campaign_id": c.campaign_id,
                    "heyreach_campaign_id": c.heyreach_campaign_id,
                    "created_at": c.created_at.isoformat() + "Z",
                    "sent_at": (c.sent_at.isoformat() + "Z") if c.sent_at else None,
                }
                for c in page_convs
            ],
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": pages,
        }


@app.get("/api/linkedin/conversations/{conv_id}")
async def get_linkedin_conversation(conv_id: int):
    """Get a single LinkedIn conversation. Runs AI classification + draft on first open."""
    with get_session() as session:
        conv = session.get(LinkedInConversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        # Lazy classification: run AI the first time this conversation is opened
        if conv.status == "pending_classification" and conv.last_message:
            try:
                category = await classify_linkedin_message(conv.last_message)
                conv.category = category

                campaign_name = ""
                if conv.campaign_id:
                    camp = session.get(LinkedInCampaign, conv.campaign_id)
                    if camp:
                        campaign_name = camp.name

                draft = ""
                if category in ("interested", "info_request", "referral"):
                    draft = await generate_linkedin_draft(
                        message=conv.last_message,
                        lead_name=conv.lead_name,
                        lead_title=conv.lead_title,
                        lead_company=conv.lead_company,
                        campaign_name=campaign_name,
                        category=category,
                    )

                conv.draft_response = draft
                conv.status = "pending_approval" if draft else "auto_handled"
                session.add(conv)
                session.commit()
                session.refresh(conv)
            except Exception as exc:
                logger.warning("Lazy classification failed for conv %s: %s", conv_id, exc)

        # Fetch full thread from HeyReach
        thread = []
        try:
            raw = await heyreach_client.get_conversation(
                account_id=conv.account_id,
                conversation_id=conv.heyreach_conversation_id,
            )
            messages = raw.get("messages", raw.get("chatRoomMessages", []))
            for msg in messages:
                thread.append({
                    "content": msg.get("message", msg.get("content", "")),
                    "sent_at": msg.get("sentAt", msg.get("timestamp", "")),
                    "is_outgoing": msg.get("isOutgoing", False),
                })
        except Exception as exc:
            logger.warning("Could not fetch HeyReach thread for conv %s: %s", conv_id, exc)

        return {
            "id": conv.id,
            "heyreach_conversation_id": conv.heyreach_conversation_id,
            "account_id": conv.account_id,
            "lead_name": conv.lead_name,
            "lead_linkedin_url": conv.lead_linkedin_url,
            "lead_title": conv.lead_title,
            "lead_company": conv.lead_company,
            "last_message": conv.last_message,
            "category": conv.category,
            "draft_response": conv.draft_response,
            "status": conv.status,
            "created_at": conv.created_at.isoformat() + "Z",
            "sent_at": (conv.sent_at.isoformat() + "Z") if conv.sent_at else None,
            "thread": thread,
        }


class LinkedInFeedbackRequest(BaseModel):
    feedback: str


@app.post("/api/linkedin/conversations/{conv_id}/feedback")
async def linkedin_conversation_feedback(conv_id: int, body: LinkedInFeedbackRequest):
    """Revise a LinkedIn draft based on feedback."""
    with get_session() as session:
        conv = session.get(LinkedInConversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

        campaign_name = ""
        if conv.campaign_id:
            camp = session.get(LinkedInCampaign, conv.campaign_id)
            if camp:
                campaign_name = camp.name

        # Re-generate using feedback as additional instruction
        new_draft = await generate_linkedin_draft(
            message=conv.last_message + f"\n\n[User feedback on previous draft: {body.feedback}]",
            lead_name=conv.lead_name,
            lead_title=conv.lead_title,
            lead_company=conv.lead_company,
            campaign_name=campaign_name,
            category=conv.category,
        )

        conv.draft_response = new_draft
        session.add(conv)
        session.commit()

        return {"id": conv_id, "draft_response": new_draft, "status": conv.status}


@app.post("/api/linkedin/conversations/{conv_id}/approve")
async def approve_linkedin_conversation(conv_id: int):
    """Approve and send a LinkedIn reply via HeyReach."""
    with get_session() as session:
        conv = session.get(LinkedInConversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        if not conv.draft_response:
            raise HTTPException(status_code=400, detail="No draft to send")

        try:
            await heyreach_client.send_message(
                conversation_id=conv.heyreach_conversation_id,
                account_id=conv.account_id,
                message=conv.draft_response,
            )
        except Exception as exc:
            logger.exception("Failed to send LinkedIn message via HeyReach")
            raise HTTPException(status_code=502, detail=f"HeyReach send error: {exc}")

        conv.status = "sent"
        conv.sent_at = datetime.utcnow()
        session.add(conv)
        session.commit()

        return {
            "status": "sent",
            "id": conv_id,
            "sent_at": conv.sent_at.isoformat() + "Z",
        }


@app.post("/api/linkedin/conversations/{conv_id}/reject")
async def reject_linkedin_conversation(conv_id: int):
    """Reject a LinkedIn conversation draft."""
    with get_session() as session:
        conv = session.get(LinkedInConversation, conv_id)
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")
        conv.status = "rejected"
        session.add(conv)
        session.commit()
        return {"status": "rejected", "id": conv_id}


# ---------------------------------------------------------------------------
# LinkedIn Analytics Dashboard
# ---------------------------------------------------------------------------

@app.get("/api/linkedin/analytics/dashboard")
async def linkedin_analytics_dashboard(
    period: str = Query("month", description="all|today|week|month"),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
):
    """Return the full LinkedIn analytics dashboard payload."""
    from datetime import timedelta

    def _period_start(p: str):
        now = datetime.utcnow()
        if p == "today":
            return now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif p == "week":
            return now - timedelta(days=7)
        elif p == "month":
            return now - timedelta(days=30)
        return None

    # --- Local conversation stats ---
    with get_session() as session:
        all_conversations = list(session.exec(select(LinkedInConversation)).all())
        all_campaigns = list(session.exec(select(LinkedInCampaign)).all())

    period_start = _period_start(period)
    conversations = [c for c in all_conversations if c.created_at >= period_start] if period_start else all_conversations

    total_conversations = len(conversations)

    by_category = {cat: 0 for cat in LINKEDIN_CATEGORIES_LIST}
    for c in conversations:
        if c.category in by_category:
            by_category[c.category] += 1

    statuses = ["pending_approval", "approved", "rejected", "sent", "auto_handled"]
    by_status = {s: 0 for s in statuses}
    for c in conversations:
        if c.status in by_status:
            by_status[c.status] += 1

    interest_rate = round(by_category["interested"] / total_conversations, 4) if total_conversations else 0.0

    response_times = []
    for c in conversations:
        if c.sent_at and c.created_at:
            delta = (c.sent_at - c.created_at).total_seconds() / 3600
            response_times.append(delta)
    avg_response_hours = round(sum(response_times) / len(response_times), 1) if response_times else 0.0

    # Daily volumes — last 30 days
    now = datetime.utcnow()
    daily_map = {}
    for c in all_conversations:
        key = c.created_at.strftime("%Y-%m-%d")
        daily_map[key] = daily_map.get(key, 0) + 1

    daily_volumes = []
    for i in range(30):
        key = (now - timedelta(days=29 - i)).strftime("%Y-%m-%d")
        daily_volumes.append({"date": key, "count": daily_map.get(key, 0)})

    # Per-campaign breakdown
    campaign_map = {}
    for c in all_conversations:
        campaign_map.setdefault(c.campaign_id, []).append(c)

    campaign_stats = []
    for camp in all_campaigns:
        camp_convs = campaign_map.get(camp.id, [])
        total = len(camp_convs)
        breakdown = {cat: sum(1 for c in camp_convs if c.category == cat) for cat in LINKEDIN_CATEGORIES_LIST}
        camp_interest_rate = round(breakdown["interested"] / total, 4) if total else 0.0
        campaign_stats.append({
            "id": camp.id,
            "heyreach_campaign_id": camp.heyreach_campaign_id,
            "name": camp.name,
            "status": camp.status,
            "total_conversations": total,
            "by_category": breakdown,
            "interest_rate": camp_interest_rate,
        })
    campaign_stats.sort(key=lambda x: x["total_conversations"], reverse=True)

    # --- HeyReach live stats ---
    if not start_date:
        start_date = (now - timedelta(days=30)).strftime("%Y-%m-%d")
    if not end_date:
        end_date = now.strftime("%Y-%m-%d")

    heyreach_stats = {}
    heyreach_error = None

    try:
        raw_stats = await heyreach_client.get_overall_stats(
            start_date=start_date,
            end_date=end_date,
        )
        by_day = raw_stats.get("byDayStats", {})
        totals = {
            "profileViews": 0,
            "messagesSent": 0,
            "totalMessageStarted": 0,
            "totalMessageReplies": 0,
            "inmailMessagesSent": 0,
            "totalInmailStarted": 0,
            "totalInmailReplies": 0,
            "connectionsSent": 0,
            "connectionsAccepted": 0,
        }
        for day_data in by_day.values():
            for key in totals:
                totals[key] += int(day_data.get(key, 0))

        acceptance_rate = (
            round(totals["connectionsAccepted"] / totals["connectionsSent"], 4)
            if totals["connectionsSent"] > 0 else 0.0
        )
        reply_rate = (
            round(totals["totalMessageReplies"] / totals["totalMessageStarted"], 4)
            if totals["totalMessageStarted"] > 0 else 0.0
        )
        inmail_reply_rate = (
            round(totals["totalInmailReplies"] / totals["totalInmailStarted"], 4)
            if totals["totalInmailStarted"] > 0 else 0.0
        )

        heyreach_stats = {
            "connections_sent": totals["connectionsSent"],
            "connections_accepted": totals["connectionsAccepted"],
            "acceptance_rate": acceptance_rate,
            "messages_sent": totals["messagesSent"],
            "messages_replied": totals["totalMessageReplies"],
            "reply_rate": reply_rate,
            "inmails_sent": totals["inmailMessagesSent"],
            "inmails_replied": totals["totalInmailReplies"],
            "inmail_reply_rate": inmail_reply_rate,
            "profile_views": totals["profileViews"],
        }
    except Exception as exc:
        logger.warning("Could not fetch HeyReach stats: %s", exc)
        heyreach_error = str(exc)
        heyreach_stats = {
            "connections_sent": 0, "connections_accepted": 0, "acceptance_rate": 0.0,
            "messages_sent": 0, "messages_replied": 0, "reply_rate": 0.0,
            "inmails_sent": 0, "inmails_replied": 0, "inmail_reply_rate": 0.0,
            "profile_views": 0,
        }

    return {
        "total_conversations": total_conversations,
        "by_category": by_category,
        "by_status": by_status,
        "interest_rate": interest_rate,
        "avg_response_hours": avg_response_hours,
        "daily_volumes": daily_volumes,
        "campaigns": campaign_stats,
        "heyreach_stats": heyreach_stats,
        "heyreach_stats_error": heyreach_error,
        "heyreach_stats_period": {"start_date": start_date, "end_date": end_date},
    }
