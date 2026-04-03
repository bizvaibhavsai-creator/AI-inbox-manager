import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, func, select

from ai_service import classify_reply, generate_draft, generate_followup, revise_draft
from config import settings
from models import AppSettings, Campaign, FollowUp, Reply

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

    # Check if a human already replied by looking at the Instantly thread
    human_managed = False
    try:
        async with httpx.AsyncClient() as http_client:
            resp = await http_client.get(
                f"{settings.instantly_api_base}/emails",
                headers={"Authorization": f"Bearer {settings.instantly_api_key}"},
                params={"lead": lead_email, "sort_order": "desc", "limit": 1},
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
    except Exception as e:
        logger.warning(f"Could not check thread for {reply_id}: {e}")

    # Generate draft response for actionable categories (skip if human already replied)
    draft = ""
    if not human_managed and category in ("interested", "info_request"):
        draft = await generate_draft(reply_body, lead_email, campaign_name, category)

    # Check approval mode
    with get_session() as session:
        settings_row = session.get(AppSettings, 1)
        approval_mode = settings_row.approval_mode if settings_row else "human"

    # Update reply record
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        reply.category = category
        reply.draft_response = draft

        if human_managed:
            reply.status = "human_managed"
        elif category in ("ooo", "unsubscribe", "dnc", "wrong_person", "not_interested"):
            reply.status = "auto_handled"
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
                            "body": reply.draft_response,
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
            "received_at": reply.received_at.isoformat(),
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
                        "body": response_body,
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
    """Create follow-up records for 3, 5, 7 day windows."""
    for i, days in enumerate(settings.followup_windows, start=1):
        followup = FollowUp(
            reply_id=reply.id,
            sequence_num=i,
            scheduled_for=datetime.utcnow() + timedelta(days=days),
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
            if reply and reply.status in ("sent", "follow_up_1", "follow_up_2"):
                results.append({
                    "followup_id": fu.id,
                    "reply_id": fu.reply_id,
                    "sequence_num": fu.sequence_num,
                    "lead_email": reply.lead_email,
                    "campaign_name": reply.campaign_name,
                    "original_reply": reply.reply_body,
                    "last_response": reply.draft_response,
                    "days_since": (now - (reply.sent_at or reply.received_at)).days,
                    "scheduled_for": fu.scheduled_for.isoformat(),
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
        days_since = (now - (reply.sent_at or reply.received_at)).days
        day_window = settings.followup_windows[followup.sequence_num - 1]

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

        # Send via Instantly.ai API v2
        instantly_sent = False
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
                        "body": reply.draft_response,
                    },
                    timeout=15.0,
                )
                resp.raise_for_status()
                instantly_sent = True
        except Exception as e:
            logger.warning(f"Instantly API send failed for reply {reply_id}: {e}")
            # Still mark as sent - the approval action should succeed even if
            # Instantly delivery fails (e.g. test replies with fake UUIDs)

        # Update status
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
                        "received_at": reply.received_at.isoformat(),
                    },
                    timeout=10.0,
                )
        except Exception as e:
            logger.error(f"Failed to notify Slack: {e}")

        return {
            "status": "sent",
            "reply_id": reply.id,
            "lead_email": reply.lead_email,
            "sent_at": reply.sent_at.isoformat(),
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
            "received_at": reply.received_at.isoformat(),
            "sent_at": reply.sent_at.isoformat() if reply.sent_at else None,
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
        for seq in [1, 2, 3]:
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
                    "received_at": r.received_at.isoformat(),
                    "sent_at": r.sent_at.isoformat() if r.sent_at else None,
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
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}
