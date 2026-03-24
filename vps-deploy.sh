#!/usr/bin/env bash
set -euo pipefail

echo "=============================================="
echo "  AI Inbox Manager — VPS Deploy Script"
echo "=============================================="

BASE="/root/inbox-manager"

# -------------------------------------------------------------------
# 1. Create directory structure
# -------------------------------------------------------------------
echo "[1/7] Creating directory structure..."
mkdir -p "$BASE/backend"
mkdir -p "$BASE/dashboard/src/app/campaigns"
mkdir -p "$BASE/dashboard/src/app/replies"
mkdir -p "$BASE/dashboard/src/components"
mkdir -p "$BASE/dashboard/src/lib"
mkdir -p "$BASE/n8n-workflows"

# -------------------------------------------------------------------
# 2. Write all files using heredocs
# -------------------------------------------------------------------
echo "[2/7] Writing project files..."

# ===== .env =====
cat << 'EOF_ENV' > "$BASE/.env"
# AI Inbox Manager — Production Environment
VPS_IP=187.77.191.67

# Instantly.ai API
INSTANTLY_API_KEY=PASTE_YOUR_INSTANTLY_KEY_HERE
INSTANTLY_WEBHOOK_SECRET=

# OpenAI
OPENAI_API_KEY=PASTE_YOUR_OPENAI_KEY_HERE

# n8n credentials
N8N_USER=admin
N8N_PASSWORD=CHANGE_THIS_PASSWORD

# n8n internal
N8N_SLACK_WEBHOOK_URL=http://n8n:5678/webhook/slack-notify
N8N_BASE_URL=http://n8n:5678

# Webhook URL (public)
WEBHOOK_URL=http://187.77.191.67:5678

# Backend public URL (dashboard calls this)
BACKEND_PUBLIC_URL=http://187.77.191.67:8888

# Google Sheets
GOOGLE_SHEET_ID=

# CORS
CORS_ORIGINS=["http://187.77.191.67:8080"]
EOF_ENV

# ===== docker-compose.prod.yml =====
cat << 'EOF_COMPOSE' > "$BASE/docker-compose.prod.yml"
version: "3.8"

services:
  backend:
    build: ./backend
    ports:
      - "8888:8888"
    volumes:
      - ./playbook.md:/app/playbook.md:ro
      - ./followups.md:/app/followups.md:ro
      - db_data:/app/data
    env_file:
      - .env
    environment:
      - DATABASE_URL=sqlite:///./data/inbox_manager.db
      - PLAYBOOK_PATH=/app/playbook.md
      - FOLLOWUPS_PATH=/app/followups.md
      - N8N_SLACK_WEBHOOK_URL=http://n8n:5678/webhook/slack-notify
      - N8N_BASE_URL=http://n8n:5678
    depends_on:
      - n8n
    restart: unless-stopped

  n8n:
    image: n8nio/n8n:latest
    ports:
      - "5678:5678"
    volumes:
      - n8n_data:/home/node/.n8n
    environment:
      - N8N_BASIC_AUTH_ACTIVE=true
      - N8N_BASIC_AUTH_USER=${N8N_USER:-admin}
      - N8N_BASIC_AUTH_PASSWORD=${N8N_PASSWORD:-changeme}
      - WEBHOOK_URL=${WEBHOOK_URL:-http://localhost:5678}
      - N8N_HOST=0.0.0.0
      - N8N_PROTOCOL=http
    restart: unless-stopped

  dashboard:
    build:
      context: ./dashboard
      args:
        - NEXT_PUBLIC_API_URL=${BACKEND_PUBLIC_URL:-http://localhost:8888}
    ports:
      - "8080:3000"
    depends_on:
      - backend
    restart: unless-stopped

volumes:
  db_data:
  n8n_data:
EOF_COMPOSE

# ===== playbook.md =====
cat << 'EOF_PLAYBOOK' > "$BASE/playbook.md"
# Messaging Playbook

> Replace this file with your actual messaging playbook. The AI will use this as context when generating draft responses.

## Tone & Style
- Professional but conversational
- Short and to the point (2-4 sentences)
- No corporate jargon
- Feel human, not automated

## Response Guidelines by Category

### Interested Prospects
- Acknowledge their interest warmly
- Propose a specific next step (call, demo, meeting)
- Include a calendar link or suggest times
- Keep urgency without being pushy

### Information Requests
- Answer their specific question concisely
- Provide the requested information (pricing, case studies, etc.)
- End with a soft CTA to continue the conversation

### Not Interested
- Thank them for their time
- Leave the door open for the future
- Don't be pushy or argumentative
- Short and respectful

### Unsubscribe
- Confirm removal immediately
- Keep it brief and professional
- Do NOT try to re-engage

### Out of Office
- Note their return date if provided
- Set a reminder to follow up after they're back
- No immediate response needed
EOF_PLAYBOOK

# ===== followups.md =====
cat << 'EOF_FOLLOWUPS' > "$BASE/followups.md"
# Follow-Up Message Templates

> Replace this file with your actual follow-up templates. The AI will use these as guides when generating follow-up messages.

## Follow-Up #1 (Day 3)
A gentle nudge. Reference your previous message and add a small piece of value (insight, stat, or social proof).

Example tone:
"Hey [Name], just circling back on my last note. [Brief value add]. Would love to find 15 minutes to chat — does [day] work?"

## Follow-Up #2 (Day 5)
A different angle. Try a new hook or approach — don't just repeat the first follow-up.

Example tone:
"Hi [Name], I know things get busy. Quick thought — [new angle or relevant insight]. Happy to share more if you're open to a quick call."

## Follow-Up #3 (Day 7)
The breakup email. Make it clear this is the last follow-up. Keep it light and leave the door open.

Example tone:
"Hi [Name], I don't want to keep filling your inbox if the timing isn't right. If things change down the road, I'm here. Wishing you all the best!"
EOF_FOLLOWUPS

# ===== backend/main.py =====
cat << 'EOF_MAIN_PY' > "$BASE/backend/main.py"
import logging
from datetime import datetime, timedelta
from typing import Optional

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlmodel import Session, SQLModel, create_engine, func, select

from ai_service import classify_reply, generate_draft, generate_followup
from config import settings
from models import Campaign, FollowUp, Reply

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

    # Generate draft response for actionable categories
    draft = ""
    if category in ("interested", "info_request", "not_interested"):
        draft = await generate_draft(reply_body, lead_email, campaign_name, category)

    # Update reply record
    with get_session() as session:
        reply = session.get(Reply, reply_id)
        reply.category = category
        reply.draft_response = draft

        if category in ("ooo", "unsubscribe", "dnc", "wrong_person"):
            reply.status = "auto_handled"
        else:
            reply.status = "pending_approval"

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
        # Don't fail the webhook - data is saved, n8n can be retried

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
                    "reply_body": r.reply_body[:200],  # Truncate for list view
                    "draft_response": r.draft_response[:200] if r.draft_response else "",
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
EOF_MAIN_PY

# ===== backend/models.py =====
cat << 'EOF_MODELS' > "$BASE/backend/models.py"
from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class Campaign(SQLModel, table=True):
    __tablename__ = "campaigns"

    id: str = Field(primary_key=True)
    name: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    replies: list["Reply"] = Relationship(back_populates="campaign")


class Reply(SQLModel, table=True):
    __tablename__ = "replies"

    id: Optional[int] = Field(default=None, primary_key=True)
    instantly_uuid: str = Field(index=True)  # reply_to_uuid from webhook
    lead_email: str = Field(index=True)
    campaign_id: str = Field(foreign_key="campaigns.id", index=True)
    campaign_name: str = ""
    reply_body: str
    reply_subject: str = ""
    category: str = ""  # interested|not_interested|ooo|unsubscribe|info_request|wrong_person|dnc
    draft_response: str = ""
    status: str = "pending_classification"
    # Status flow: pending_classification -> pending_approval -> approved -> sent
    #              pending_classification -> auto_handled (for ooo/unsubscribe)
    #              pending_approval -> rejected
    #              sent -> follow_up_1 -> follow_up_2 -> follow_up_3
    received_at: datetime = Field(default_factory=datetime.utcnow)
    approved_at: Optional[datetime] = None
    sent_at: Optional[datetime] = None
    approved_by: str = ""  # Slack user who approved
    created_at: datetime = Field(default_factory=datetime.utcnow)

    campaign: Optional[Campaign] = Relationship(back_populates="replies")
    follow_ups: list["FollowUp"] = Relationship(back_populates="reply")


class FollowUp(SQLModel, table=True):
    __tablename__ = "follow_ups"

    id: Optional[int] = Field(default=None, primary_key=True)
    reply_id: int = Field(foreign_key="replies.id", index=True)
    sequence_num: int  # 1, 2, or 3
    follow_up_body: str = ""
    status: str = "pending"  # pending|sent|cancelled
    scheduled_for: datetime
    sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)

    reply: Optional[Reply] = Relationship(back_populates="follow_ups")
EOF_MODELS

# ===== backend/ai_service.py =====
cat << 'EOF_AI_SERVICE' > "$BASE/backend/ai_service.py"
import re
from pathlib import Path

from openai import AsyncOpenAI

from config import settings

client = AsyncOpenAI(api_key=settings.openai_api_key) if settings.openai_api_key else None

CATEGORIES = [
    "interested",
    "not_interested",
    "unsubscribe",
    "ooo",
    "info_request",
    "wrong_person",
    "dnc",  # do not contact
]

CLASSIFICATION_PROMPT = """You are an expert at classifying B2B cold email responses.
Analyze the email reply below and classify it into exactly ONE of these categories:

- interested: The prospect expresses interest, wants to learn more, asks for a call/demo, or gives a positive signal
- not_interested: The prospect explicitly declines, says not a fit, or gives a clear negative response
- unsubscribe: The prospect asks to be removed from the mailing list, says stop emailing, or similar
- ooo: Out of office / auto-reply / vacation message / away message
- info_request: The prospect asks for more information, pricing, case studies, or specifics before committing
- wrong_person: The prospect says they're not the right contact or redirects to someone else
- dnc: Do not contact - legal threats, hostile responses, or explicit cease & desist

Respond with ONLY the category name, nothing else.

Email reply:
{reply_body}"""

DRAFT_RESPONSE_PROMPT = """You are a B2B cold email expert writing a follow-up response on behalf of a sales agency.

You must follow the messaging playbook below EXACTLY for tone, style, and approach.

MESSAGING PLAYBOOK:
{playbook}

CONTEXT:
- Lead email: {lead_email}
- Campaign: {campaign_name}
- Their reply category: {category}
- Their original reply: {reply_body}

Write a response that:
1. Matches the playbook tone and style
2. Is appropriate for the "{category}" category
3. Is concise (2-4 sentences max)
4. Feels human and personalized, not templated
5. Includes a clear next step or CTA if appropriate

Write ONLY the email body text. No subject line, no greeting prefix like "Hi [Name]" unless the playbook specifies it."""

FOLLOWUP_PROMPT = """You are a B2B cold email expert writing a follow-up message.

FOLLOW-UP TEMPLATES:
{followup_templates}

CONTEXT:
- Lead email: {lead_email}
- Campaign: {campaign_name}
- Original reply from prospect: {original_reply}
- Our last response: {last_response}
- This is follow-up #{sequence_num} (day {day_window})
- Days since last contact: {days_since}

Using the follow-up template for sequence #{sequence_num} as a guide, write a personalized follow-up.
Keep it short (1-3 sentences). Make it feel natural, not automated.

Write ONLY the email body text."""


def _load_file(path: str) -> str:
    """Load a text file, return empty string if not found."""
    try:
        return Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


async def classify_reply(reply_body: str) -> str:
    """Classify an email reply into a category using GPT-4o-mini."""
    if not client or settings.test_mode:
        return _mock_classify(reply_body)

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": CLASSIFICATION_PROMPT.format(reply_body=reply_body),
            }
        ],
        temperature=0,
        max_tokens=20,
    )
    category = response.choices[0].message.content.strip().lower()
    # Validate category
    if category not in CATEGORIES:
        return "not_interested"  # Safe fallback
    return category


def _mock_classify(reply_body: str) -> str:
    """Simple keyword-based classification for testing without OpenAI."""
    body = reply_body.lower()
    if any(w in body for w in ["unsubscribe", "remove me", "stop emailing", "opt out"]):
        return "unsubscribe"
    if any(w in body for w in ["out of office", "ooo", "vacation", "away", "auto-reply", "returning"]):
        return "ooo"
    if any(w in body for w in ["wrong person", "not the right contact", "try reaching", "redirect"]):
        return "wrong_person"
    if any(w in body for w in ["interested", "love to", "schedule", "call", "demo", "let's chat", "sounds great", "tell me more"]):
        return "interested"
    if any(w in body for w in ["pricing", "case study", "more info", "how much", "details", "brochure"]):
        return "info_request"
    if any(w in body for w in ["not interested", "no thanks", "not a fit", "pass", "not for us", "decline"]):
        return "not_interested"
    return "not_interested"


async def generate_draft(
    reply_body: str,
    lead_email: str,
    campaign_name: str,
    category: str,
) -> str:
    """Generate a draft response using the messaging playbook."""
    if not client or settings.test_mode:
        return _mock_draft(lead_email, category)

    playbook = _load_file(settings.playbook_path)
    if not playbook:
        playbook = "(No playbook provided - use professional B2B sales best practices)"

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": DRAFT_RESPONSE_PROMPT.format(
                    playbook=playbook,
                    lead_email=lead_email,
                    campaign_name=campaign_name,
                    category=category,
                    reply_body=reply_body,
                ),
            }
        ],
        temperature=0.7,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def _mock_draft(lead_email: str, category: str) -> str:
    """Return a mock draft for testing without OpenAI."""
    name = lead_email.split("@")[0].title()
    drafts = {
        "interested": f"Hi {name}, great to hear you're interested! I'd love to set up a quick 15-minute call to walk you through everything. What does your schedule look like this week?",
        "info_request": f"Hi {name}, happy to share more details! I've attached a brief overview. Would it help to hop on a quick call to go deeper into specifics?",
        "not_interested": f"Hi {name}, totally understand — appreciate you letting me know. If things change down the road, feel free to reach out. Wishing you all the best!",
    }
    return drafts.get(category, f"Hi {name}, thanks for getting back to me!")


async def generate_followup(
    lead_email: str,
    campaign_name: str,
    original_reply: str,
    last_response: str,
    sequence_num: int,
    day_window: int,
    days_since: int,
) -> str:
    """Generate a follow-up message using the follow-up templates."""
    if not client or settings.test_mode:
        return _mock_followup(lead_email, sequence_num)

    followup_templates = _load_file(settings.followups_path)
    if not followup_templates:
        followup_templates = (
            "(No follow-up templates provided - use professional B2B follow-up best practices)"
        )

    response = await client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": FOLLOWUP_PROMPT.format(
                    followup_templates=followup_templates,
                    lead_email=lead_email,
                    campaign_name=campaign_name,
                    original_reply=original_reply,
                    last_response=last_response,
                    sequence_num=sequence_num,
                    day_window=day_window,
                    days_since=days_since,
                ),
            }
        ],
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()


def _mock_followup(lead_email: str, sequence_num: int) -> str:
    """Return a mock follow-up for testing without OpenAI."""
    name = lead_email.split("@")[0].title()
    followups = {
        1: f"Hey {name}, just bumping this to the top of your inbox. Would love to find 15 minutes to chat — does this week work?",
        2: f"Hi {name}, different angle — we just helped a similar company increase their pipeline by 3x. Happy to share how if you're open to a quick call.",
        3: f"Hey {name}, last note from me — don't want to clog your inbox. If things change, I'm here. All the best!",
    }
    return followups.get(sequence_num, f"Hi {name}, just following up on my previous message.")
EOF_AI_SERVICE

# ===== backend/config.py =====
cat << 'EOF_CONFIG' > "$BASE/backend/config.py"
import os
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Instantly.ai
    instantly_api_key: str = ""
    instantly_webhook_secret: str = ""  # Optional: verify webhook authenticity

    # OpenAI
    openai_api_key: str = ""

    # n8n internal webhook URLs
    n8n_slack_webhook_url: str = "http://n8n:5678/webhook/slack-notify"
    n8n_base_url: str = "http://n8n:5678"

    # Google Sheets (handled by n8n, but sheet ID needed for reference)
    google_sheet_id: str = ""

    # Database
    database_url: str = "sqlite:///./inbox_manager.db"

    # Playbook paths
    playbook_path: str = str(Path(__file__).parent.parent / "playbook.md")
    followups_path: str = str(Path(__file__).parent.parent / "followups.md")

    # Follow-up windows (days)
    followup_windows: list[int] = [3, 5, 7]

    # API base URLs
    instantly_api_base: str = "https://api.instantly.ai/api/v2"

    # CORS origins for dashboard
    cors_origins: list[str] = ["http://localhost:8080", "http://localhost:3000"]

    # Test mode - uses mock AI responses when API keys aren't set
    test_mode: bool = False

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
EOF_CONFIG

# ===== backend/requirements.txt =====
cat << 'EOF_REQUIREMENTS' > "$BASE/backend/requirements.txt"
fastapi==0.115.6
uvicorn[standard]==0.34.0
sqlmodel==0.0.22
pydantic-settings==2.7.1
openai==1.59.7
httpx==0.28.1
EOF_REQUIREMENTS

# ===== backend/Dockerfile =====
cat << 'EOF_BACKEND_DOCKER' > "$BASE/backend/Dockerfile"
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888"]
EOF_BACKEND_DOCKER

# ===== dashboard/package.json =====
cat << 'EOF_PACKAGE_JSON' > "$BASE/dashboard/package.json"
{
  "name": "inbox-manager-dashboard",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start"
  },
  "dependencies": {
    "@tailwindcss/postcss": "^4.2.2",
    "@types/node": "^25.5.0",
    "@types/react": "^19.2.14",
    "next": "^16.2.1",
    "postcss": "^8.5.8",
    "react": "^19.2.4",
    "react-dom": "^19.2.4",
    "recharts": "^3.8.0",
    "tailwindcss": "^4.2.2",
    "typescript": "^6.0.2"
  }
}
EOF_PACKAGE_JSON

# ===== dashboard/tsconfig.json =====
cat << 'EOF_TSCONFIG' > "$BASE/dashboard/tsconfig.json"
{
  "compilerOptions": {
    "target": "ES2017",
    "lib": [
      "dom",
      "dom.iterable",
      "esnext"
    ],
    "allowJs": true,
    "skipLibCheck": true,
    "strict": true,
    "noEmit": true,
    "esModuleInterop": true,
    "module": "esnext",
    "moduleResolution": "bundler",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "jsx": "react-jsx",
    "incremental": true,
    "plugins": [
      {
        "name": "next"
      }
    ],
    "paths": {
      "@/*": [
        "./src/*"
      ]
    }
  },
  "include": [
    "next-env.d.ts",
    "**/*.ts",
    "**/*.tsx",
    ".next/types/**/*.ts",
    ".next/dev/types/**/*.ts"
  ],
  "exclude": [
    "node_modules"
  ]
}
EOF_TSCONFIG

# ===== dashboard/postcss.config.mjs =====
cat << 'EOF_POSTCSS' > "$BASE/dashboard/postcss.config.mjs"
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
EOF_POSTCSS

# ===== dashboard/Dockerfile =====
cat << 'EOF_DASH_DOCKER' > "$BASE/dashboard/Dockerfile"
FROM node:20-alpine

WORKDIR /app

ARG NEXT_PUBLIC_API_URL=http://localhost:8888
ENV NEXT_PUBLIC_API_URL=$NEXT_PUBLIC_API_URL

COPY package.json package-lock.json* ./
RUN npm install

COPY . .

RUN npm run build

EXPOSE 3000
CMD ["npm", "start"]
EOF_DASH_DOCKER

# ===== dashboard/src/app/globals.css =====
cat << 'EOF_GLOBALS_CSS' > "$BASE/dashboard/src/app/globals.css"
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
@import "tailwindcss";

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
  background-color: #eef1f6;
  -webkit-font-smoothing: antialiased;
}
EOF_GLOBALS_CSS

# ===== dashboard/src/app/layout.tsx =====
cat << 'EOF_LAYOUT' > "$BASE/dashboard/src/app/layout.tsx"
import type { Metadata } from "next";
import "./globals.css";
import Sidebar from "@/components/Sidebar";

export const metadata: Metadata = {
  title: "AI Inbox Manager",
  description: "Cold email response analytics dashboard",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="antialiased" style={{ color: "#1a1a2e" }}>
        <Sidebar />
        <main className="ml-60 min-h-screen p-8">{children}</main>
      </body>
    </html>
  );
}
EOF_LAYOUT

# ===== dashboard/src/app/page.tsx =====
cat << 'EOF_PAGE' > "$BASE/dashboard/src/app/page.tsx"
"use client";

import { useEffect, useState } from "react";
import KPICard from "@/components/KPICard";
import CategoryPieChart from "@/components/CategoryPieChart";
import TimelineChart from "@/components/TimelineChart";
import PeriodFilter from "@/components/PeriodFilter";
import {
  getStatsOverview,
  getTimeline,
  getResponseTimes,
  getFollowUpStats,
  type StatsOverview,
  type TimelineEntry,
  type ResponseTimes,
  type FollowUpStats,
} from "@/lib/api";

export default function OverviewPage() {
  const [period, setPeriod] = useState("all");
  const [overview, setOverview] = useState<StatsOverview | null>(null);
  const [timeline, setTimeline] = useState<TimelineEntry[]>([]);
  const [responseTimes, setResponseTimes] = useState<ResponseTimes | null>(null);
  const [followUps, setFollowUps] = useState<FollowUpStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const [ov, tl, rt, fu] = await Promise.all([
          getStatsOverview(period),
          getTimeline(30),
          getResponseTimes(),
          getFollowUpStats(),
        ]);
        setOverview(ov);
        setTimeline(tl.timeline);
        setResponseTimes(rt);
        setFollowUps(fu);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [period]);

  if (error) {
    return (
      <div className="flex h-64 items-center justify-center">
        <div className="rounded-2xl bg-white p-8 text-center" style={{ border: "1px solid #e2e6ee" }}>
          <p className="text-[14px] font-medium" style={{ color: "#ef4444" }}>{error}</p>
          <p className="mt-2 text-[12px]" style={{ color: "#a5abbe" }}>
            Make sure the backend is running on {process.env.NEXT_PUBLIC_API_URL || "http://localhost:8888"}
          </p>
        </div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
            Overview
          </h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "#8a91a5" }}>
            Real-time inbox management analytics
          </p>
        </div>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-[#e2e6ee]" style={{ borderTopColor: "#3366FF" }} />
        </div>
      ) : overview ? (
        <>
          {/* KPI Cards */}
          <div className="mb-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard title="Total Responses" value={overview.total} color="indigo" />
            <KPICard title="Interested" value={overview.interested} color="green" />
            <KPICard title="Not Interested" value={overview.not_interested} color="red" />
            <KPICard title="Out of Office" value={overview.ooo} color="yellow" />
          </div>

          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard title="Unsubscribe" value={overview.unsubscribe} color="gray" />
            <KPICard title="Info Request" value={overview.info_request} color="purple" />
            <KPICard
              title="Pending Approval"
              value={overview.pending_approval}
              color="orange"
              subtitle="Awaiting Slack response"
            />
            <KPICard
              title="Sent"
              value={overview.sent}
              color="green"
              subtitle={
                overview.approval_rate
                  ? `${overview.approval_rate.toFixed(0)}% approval rate`
                  : undefined
              }
            />
          </div>

          {/* Response time cards */}
          {responseTimes && (
            <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-3">
              <KPICard
                title="Avg Approval Time"
                value={
                  responseTimes.avg_approval_time_minutes
                    ? `${responseTimes.avg_approval_time_minutes.toFixed(0)} min`
                    : "N/A"
                }
                color="purple"
              />
              <KPICard
                title="Avg Response Time"
                value={
                  responseTimes.avg_send_time_minutes
                    ? `${responseTimes.avg_send_time_minutes.toFixed(0)} min`
                    : "N/A"
                }
                color="blue"
              />
              <KPICard
                title="Total Sent"
                value={responseTimes.total_sent}
                color="green"
              />
            </div>
          )}

          {/* Charts */}
          <div className="mb-8 grid gap-5 lg:grid-cols-2">
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Category Breakdown
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Distribution of reply types
              </p>
              <CategoryPieChart data={overview} />
            </div>
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Daily Volume
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Last 30 days
              </p>
              <TimelineChart data={timeline} />
            </div>
          </div>

          {/* Follow-up stats */}
          {followUps && followUps.total > 0 && (
            <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
              <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
                Follow-Up Stats
              </h2>
              <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
                Automated follow-up sequences
              </p>
              <div className="grid grid-cols-3 gap-4">
                {Object.entries(followUps.by_sequence).map(([key, val]) => (
                  <div
                    key={key}
                    className="rounded-xl p-4 text-center"
                    style={{ backgroundColor: "#f8f9fc" }}
                  >
                    <p className="text-[11px] font-medium" style={{ color: "#8a91a5" }}>
                      {key.replace("_", " ").replace("followup", "Follow-up #")}
                    </p>
                    <p className="mt-1 text-[24px] font-semibold" style={{ color: "#1a1a2e" }}>
                      {val.sent}
                    </p>
                    <p className="text-[11px]" style={{ color: "#a5abbe" }}>
                      of {val.total} scheduled
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      ) : null}
    </div>
  );
}
EOF_PAGE

# ===== dashboard/src/app/campaigns/page.tsx =====
cat << 'EOF_CAMPAIGNS' > "$BASE/dashboard/src/app/campaigns/page.tsx"
"use client";

import { useEffect, useState } from "react";
import CampaignTable from "@/components/CampaignTable";
import CampaignBarChart from "@/components/CampaignBarChart";
import PeriodFilter from "@/components/PeriodFilter";
import KPICard from "@/components/KPICard";
import { getCampaignStats, type CampaignStats } from "@/lib/api";

export default function CampaignsPage() {
  const [period, setPeriod] = useState("all");
  const [campaigns, setCampaigns] = useState<CampaignStats[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getCampaignStats(period);
        setCampaigns(data.campaigns);
      } catch (e) {
        setError(e instanceof Error ? e.message : "Failed to load data");
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [period]);

  const bestCampaign = campaigns.reduce(
    (best, c) => (c.interest_rate > (best?.interest_rate ?? 0) ? c : best),
    null as CampaignStats | null
  );
  const worstCampaign = campaigns.reduce(
    (worst, c) =>
      c.total >= 5 && c.interest_rate < (worst?.interest_rate ?? 100)
        ? c
        : worst,
    null as CampaignStats | null
  );
  const highUnsubCampaign = campaigns.find(
    (c) => c.total >= 10 && c.unsubscribe / c.total > 0.05
  );

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        <div>
          <h1 className="text-[22px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
            Campaigns
          </h1>
          <p className="mt-0.5 text-[13px]" style={{ color: "#8a91a5" }}>
            Per-campaign response breakdown
          </p>
        </div>
        <PeriodFilter value={period} onChange={setPeriod} />
      </div>

      {loading ? (
        <div className="flex h-64 items-center justify-center">
          <div className="h-7 w-7 animate-spin rounded-full border-[3px] border-[#e2e6ee]" style={{ borderTopColor: "#3366FF" }} />
        </div>
      ) : error ? (
        <div className="rounded-2xl bg-white p-8 text-center" style={{ border: "1px solid #e2e6ee", color: "#ef4444" }}>
          {error}
        </div>
      ) : (
        <>
          {/* Quick KPIs */}
          <div className="mb-8 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <KPICard
              title="Total Campaigns"
              value={campaigns.length}
              color="indigo"
            />
            {bestCampaign && (
              <KPICard
                title="Best Campaign"
                value={`${bestCampaign.interest_rate}%`}
                subtitle={bestCampaign.campaign_name}
                color="green"
              />
            )}
            {worstCampaign && (
              <KPICard
                title="Lowest Interest Rate"
                value={`${worstCampaign.interest_rate}%`}
                subtitle={worstCampaign.campaign_name}
                color="red"
              />
            )}
            {highUnsubCampaign && (
              <KPICard
                title="High Unsubscribe Alert"
                value={`${((highUnsubCampaign.unsubscribe / highUnsubCampaign.total) * 100).toFixed(1)}%`}
                subtitle={highUnsubCampaign.campaign_name}
                color="orange"
              />
            )}
          </div>

          {/* Stacked bar chart */}
          <div className="mb-6 rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
            <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
              Category Distribution by Campaign
            </h2>
            <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
              Stacked breakdown per campaign
            </p>
            <CampaignBarChart campaigns={campaigns} />
          </div>

          {/* Campaign table */}
          <div className="rounded-2xl bg-white p-6" style={{ border: "1px solid #e2e6ee" }}>
            <h2 className="mb-1 text-[14px] font-semibold" style={{ color: "#1a1a2e" }}>
              All Campaigns
            </h2>
            <p className="mb-4 text-[11px]" style={{ color: "#a5abbe" }}>
              Sorted by total replies
            </p>
            <CampaignTable campaigns={campaigns} />
          </div>
        </>
      )}
    </div>
  );
}
EOF_CAMPAIGNS

# ===== dashboard/src/app/replies/page.tsx =====
cat << 'EOF_REPLIES' > "$BASE/dashboard/src/app/replies/page.tsx"
"use client";

import { useEffect, useState } from "react";
import { getReplies, type ReplyItem } from "@/lib/api";

const categoryStyles: Record<string, { bg: string; color: string; label: string }> = {
  interested: { bg: "#eef2ff", color: "#3366FF", label: "Interested" },
  not_interested: { bg: "#fef2f2", color: "#ef4444", label: "Not Interested" },
  ooo: { bg: "#fffbeb", color: "#d97706", label: "OOO" },
  unsubscribe: { bg: "#f3f4f6", color: "#6b7280", label: "Unsubscribe" },
  info_request: { bg: "#eef2ff", color: "#6366f1", label: "Info Request" },
  wrong_person: { bg: "#f5f3ff", color: "#8b5cf6", label: "Wrong Person" },
  dnc: { bg: "#fef2f2", color: "#dc2626", label: "DNC" },
};

const statusStyles: Record<string, { bg: string; color: string; label: string }> = {
  pending_approval: { bg: "#fff7ed", color: "#ea580c", label: "Pending" },
  approved: { bg: "#eef2ff", color: "#3366FF", label: "Approved" },
  sent: { bg: "#f0fdf4", color: "#16a34a", label: "Sent" },
  rejected: { bg: "#fef2f2", color: "#ef4444", label: "Rejected" },
  auto_handled: { bg: "#f3f4f6", color: "#6b7280", label: "Auto" },
};

export default function RepliesPage() {
  const [replies, setReplies] = useState<ReplyItem[]>([]);
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [loading, setLoading] = useState(true);
  const [selectedId, setSelectedId] = useState<number | null>(null);

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const data = await getReplies(
          page,
          categoryFilter || undefined,
          statusFilter || undefined
        );
        setReplies(data.replies);
        setTotalPages(data.pages);
        setTotal(data.total);
      } catch {
        // API not available yet
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [page, categoryFilter, statusFilter]);

  const selectedReply = replies.find((r) => r.id === selectedId);

  return (
    <div className="flex gap-0" style={{ height: "calc(100vh - 64px)" }}>
      {/* Left panel — inbox list */}
      <div
        className="flex flex-col overflow-hidden rounded-2xl bg-white"
        style={{
          border: "1px solid #e2e6ee",
          width: selectedId ? "420px" : "100%",
          minWidth: "420px",
          transition: "width 0.2s ease",
        }}
      >
        {/* Header */}
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid #e2e6ee" }}
        >
          <div>
            <h1 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
              Inbox
            </h1>
            <p className="text-[11px]" style={{ color: "#a5abbe" }}>
              {total} replies
            </p>
          </div>
          <div className="flex gap-2">
            <select
              value={categoryFilter}
              onChange={(e) => {
                setCategoryFilter(e.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Categories</option>
              <option value="interested">Interested</option>
              <option value="not_interested">Not Interested</option>
              <option value="ooo">OOO</option>
              <option value="unsubscribe">Unsubscribe</option>
              <option value="info_request">Info Request</option>
              <option value="wrong_person">Wrong Person</option>
            </select>
            <select
              value={statusFilter}
              onChange={(e) => {
                setStatusFilter(e.target.value);
                setPage(1);
                setSelectedId(null);
              }}
              className="rounded-lg bg-transparent px-2 py-1.5 text-[11px] font-medium outline-none"
              style={{ border: "1px solid #e2e6ee", color: "#5a6176" }}
            >
              <option value="">All Statuses</option>
              <option value="pending_approval">Pending</option>
              <option value="sent">Sent</option>
              <option value="rejected">Rejected</option>
              <option value="auto_handled">Auto</option>
            </select>
          </div>
        </div>

        {/* Reply rows */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="flex h-40 items-center justify-center">
              <div
                className="h-6 w-6 animate-spin rounded-full border-[2.5px] border-[#e2e6ee]"
                style={{ borderTopColor: "#3366FF" }}
              />
            </div>
          ) : replies.length === 0 ? (
            <div className="flex h-40 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
              No replies found
            </div>
          ) : (
            replies.map((r) => {
              const catStyle = categoryStyles[r.category] || { bg: "#f3f4f6", color: "#6b7280", label: r.category };
              const isActive = selectedId === r.id;

              return (
                <div
                  key={r.id}
                  onClick={() => setSelectedId(isActive ? null : r.id)}
                  className="flex cursor-pointer items-center gap-3 px-5 py-3 transition-colors"
                  style={{
                    borderBottom: "1px solid #f0f2f7",
                    backgroundColor: isActive ? "#f0f4ff" : "transparent",
                  }}
                  onMouseEnter={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "#f8f9fc";
                  }}
                  onMouseLeave={(e) => {
                    if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
                  }}
                >
                  {/* Category tag — left side */}
                  <span
                    className="shrink-0 rounded-md px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                    style={{ backgroundColor: catStyle.bg, color: catStyle.color, minWidth: "56px", textAlign: "center" }}
                  >
                    {catStyle.label}
                  </span>

                  {/* Email + preview */}
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span
                        className="truncate text-[13px] font-semibold"
                        style={{ color: "#1a1a2e", maxWidth: selectedId ? "140px" : "240px" }}
                      >
                        {r.lead_email.split("@")[0]}
                      </span>
                      <span className="truncate text-[12px] font-medium" style={{ color: "#5a6176" }}>
                        {r.reply_body.slice(0, 60)}...
                      </span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px]" style={{ color: "#a5abbe" }}>
                      {r.campaign_name}
                    </p>
                  </div>

                  {/* Time + status */}
                  <div className="shrink-0 text-right">
                    <p className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
                      {new Date(r.received_at).toLocaleTimeString("en-US", {
                        hour: "numeric",
                        minute: "2-digit",
                        hour12: true,
                      })}
                    </p>
                    {r.status !== "auto_handled" && (
                      <span
                        className="mt-0.5 inline-block rounded px-1 py-0.5 text-[8px] font-bold uppercase tracking-wider"
                        style={{
                          backgroundColor: (statusStyles[r.status] || statusStyles.auto_handled).bg,
                          color: (statusStyles[r.status] || statusStyles.auto_handled).color,
                        }}
                      >
                        {(statusStyles[r.status] || statusStyles.auto_handled).label}
                      </span>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div
            className="flex items-center justify-between px-5 py-3"
            style={{ borderTop: "1px solid #e2e6ee" }}
          >
            <button
              onClick={() => { setPage((p) => Math.max(1, p - 1)); setSelectedId(null); }}
              disabled={page === 1}
              className="text-[11px] font-medium disabled:opacity-30"
              style={{ color: "#5a6176" }}
            >
              &larr; Prev
            </button>
            <span className="text-[11px] font-medium" style={{ color: "#a5abbe" }}>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => { setPage((p) => Math.min(totalPages, p + 1)); setSelectedId(null); }}
              disabled={page === totalPages}
              className="text-[11px] font-medium disabled:opacity-30"
              style={{ color: "#5a6176" }}
            >
              Next &rarr;
            </button>
          </div>
        )}
      </div>

      {/* Right panel — conversation detail */}
      {selectedId && selectedReply && (
        <div
          className="ml-5 flex flex-1 flex-col overflow-hidden rounded-2xl bg-white"
          style={{ border: "1px solid #e2e6ee" }}
        >
          {/* Detail header */}
          <div
            className="flex items-center justify-between px-6 py-4"
            style={{ borderBottom: "1px solid #e2e6ee" }}
          >
            <div>
              <h2 className="text-[15px] font-semibold" style={{ color: "#1a1a2e" }}>
                {selectedReply.lead_email}
              </h2>
              <p className="mt-0.5 text-[11px]" style={{ color: "#a5abbe" }}>
                {selectedReply.campaign_name} &middot;{" "}
                {new Date(selectedReply.received_at).toLocaleDateString("en-US", {
                  month: "short",
                  day: "numeric",
                  year: "numeric",
                  hour: "numeric",
                  minute: "2-digit",
                })}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <span
                className="rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                style={{
                  backgroundColor: (categoryStyles[selectedReply.category] || categoryStyles.interested).bg,
                  color: (categoryStyles[selectedReply.category] || categoryStyles.interested).color,
                }}
              >
                {(categoryStyles[selectedReply.category] || { label: selectedReply.category }).label}
              </span>
              <span
                className="rounded-lg px-2.5 py-1 text-[10px] font-bold uppercase tracking-wider"
                style={{
                  backgroundColor: (statusStyles[selectedReply.status] || statusStyles.auto_handled).bg,
                  color: (statusStyles[selectedReply.status] || statusStyles.auto_handled).color,
                }}
              >
                {(statusStyles[selectedReply.status] || statusStyles.auto_handled).label}
              </span>
              <button
                onClick={() => setSelectedId(null)}
                className="ml-2 rounded-lg p-1.5 transition-colors hover:bg-[#f5f7fa]"
              >
                <svg className="h-4 w-4" fill="none" stroke="#8a91a5" strokeWidth={2} viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
          </div>

          {/* Conversation thread */}
          <div className="flex-1 overflow-y-auto px-6 py-5">
            {/* Their reply */}
            <div className="mb-6">
              <div className="mb-2 flex items-center gap-2">
                <div
                  className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold text-white"
                  style={{ backgroundColor: "#3366FF" }}
                >
                  {selectedReply.lead_email.charAt(0).toUpperCase()}
                </div>
                <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                  {selectedReply.lead_email}
                </span>
                <span className="text-[11px]" style={{ color: "#a5abbe" }}>
                  {new Date(selectedReply.received_at).toLocaleTimeString("en-US", {
                    hour: "numeric",
                    minute: "2-digit",
                    hour12: true,
                  })}
                </span>
              </div>
              <div
                className="ml-9 rounded-xl p-4"
                style={{ backgroundColor: "#f8f9fc", border: "1px solid #eef1f6" }}
              >
                <p className="text-[13px] leading-relaxed" style={{ color: "#3d4254" }}>
                  {selectedReply.reply_body}
                </p>
              </div>
            </div>

            {/* AI Draft response */}
            {selectedReply.draft_response && (
              <div>
                <div className="mb-2 flex items-center gap-2">
                  <div
                    className="flex h-7 w-7 items-center justify-center rounded-full text-[11px] font-bold"
                    style={{ backgroundColor: "#eef2ff", color: "#3366FF" }}
                  >
                    AI
                  </div>
                  <span className="text-[12px] font-semibold" style={{ color: "#1a1a2e" }}>
                    AI Draft Response
                  </span>
                  <span
                    className="rounded px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-wider"
                    style={{ backgroundColor: "#fffbeb", color: "#d97706" }}
                  >
                    Draft
                  </span>
                </div>
                <div
                  className="ml-9 rounded-xl p-4"
                  style={{ backgroundColor: "#f0f4ff", border: "1px solid #dde4f8" }}
                >
                  <p className="text-[13px] leading-relaxed" style={{ color: "#2d3a6e" }}>
                    {selectedReply.draft_response}
                  </p>
                </div>
              </div>
            )}

            {/* Sent timestamp */}
            {selectedReply.sent_at && (
              <div className="mt-6 flex items-center gap-2">
                <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
                <span className="text-[10px] font-medium uppercase tracking-wider" style={{ color: "#a5abbe" }}>
                  Sent {new Date(selectedReply.sent_at).toLocaleDateString("en-US", {
                    month: "short",
                    day: "numeric",
                    hour: "numeric",
                    minute: "2-digit",
                  })}
                </span>
                <div className="h-px flex-1" style={{ backgroundColor: "#e2e6ee" }} />
              </div>
            )}
          </div>

          {/* Bottom info bar */}
          <div
            className="flex items-center gap-4 px-6 py-3"
            style={{ borderTop: "1px solid #e2e6ee", backgroundColor: "#fafbfd" }}
          >
            <span className="text-[11px]" style={{ color: "#a5abbe" }}>
              Reply managed via Slack approval workflow
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
EOF_REPLIES

# ===== dashboard/src/components/KPICard.tsx =====
cat << 'EOF_KPICARD' > "$BASE/dashboard/src/components/KPICard.tsx"
"use client";

interface KPICardProps {
  title: string;
  value: number | string;
  subtitle?: string;
  color?: string;
}

const iconColors: Record<string, { dot: string; bg: string }> = {
  blue: { dot: "#3366FF", bg: "#eef2ff" },
  green: { dot: "#22c55e", bg: "#f0fdf4" },
  red: { dot: "#ef4444", bg: "#fef2f2" },
  yellow: { dot: "#f59e0b", bg: "#fffbeb" },
  purple: { dot: "#8b5cf6", bg: "#f5f3ff" },
  gray: { dot: "#6b7280", bg: "#f3f4f6" },
  orange: { dot: "#f97316", bg: "#fff7ed" },
  indigo: { dot: "#3366FF", bg: "#eef2ff" },
};

export default function KPICard({ title, value, subtitle, color = "blue" }: KPICardProps) {
  const scheme = iconColors[color] || iconColors.blue;

  return (
    <div
      className="rounded-2xl bg-white p-5"
      style={{ border: "1px solid #e2e6ee" }}
    >
      <div className="flex items-center gap-2">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ backgroundColor: scheme.dot }}
        />
        <p className="text-[12px] font-medium tracking-wide" style={{ color: "#8a91a5" }}>
          {title}
        </p>
      </div>
      <p className="mt-2 text-[28px] font-semibold leading-none tracking-tight" style={{ color: "#1a1a2e" }}>
        {value}
      </p>
      {subtitle && (
        <p className="mt-1.5 text-[11px] font-medium" style={{ color: "#a5abbe" }}>
          {subtitle}
        </p>
      )}
    </div>
  );
}
EOF_KPICARD

# ===== dashboard/src/components/CategoryPieChart.tsx =====
cat << 'EOF_PIECHART' > "$BASE/dashboard/src/components/CategoryPieChart.tsx"
"use client";

import { PieChart, Pie, Cell, Legend, Tooltip, ResponsiveContainer } from "recharts";
import type { StatsOverview } from "@/lib/api";

const COLORS: Record<string, string> = {
  Interested: "#3366FF",
  "Not Interested": "#ef4444",
  OOO: "#f59e0b",
  Unsubscribe: "#94a3b8",
  "Info Request": "#6366f1",
  "Wrong Person": "#a78bfa",
  DNC: "#dc2626",
};

interface Props {
  data: StatsOverview;
}

export default function CategoryPieChart({ data }: Props) {
  const chartData = [
    { name: "Interested", value: data.interested },
    { name: "Not Interested", value: data.not_interested },
    { name: "OOO", value: data.ooo },
    { name: "Unsubscribe", value: data.unsubscribe },
    { name: "Info Request", value: data.info_request },
    { name: "Wrong Person", value: data.wrong_person },
    { name: "DNC", value: data.dnc },
  ].filter((d) => d.value > 0);

  if (chartData.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300}>
      <PieChart>
        <Pie
          data={chartData}
          cx="50%"
          cy="50%"
          innerRadius={65}
          outerRadius={105}
          paddingAngle={4}
          dataKey="value"
          stroke="none"
          label={({ name, percent }) =>
            `${name} ${((percent ?? 0) * 100).toFixed(0)}%`
          }
        >
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={COLORS[entry.name] || "#94a3b8"} />
          ))}
        </Pie>
        <Tooltip
          contentStyle={{
            borderRadius: "12px",
            border: "1px solid #e2e6ee",
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
            fontSize: "12px",
            fontFamily: "Inter",
          }}
        />
        <Legend
          wrapperStyle={{ fontSize: "12px", fontFamily: "Inter" }}
        />
      </PieChart>
    </ResponsiveContainer>
  );
}
EOF_PIECHART

# ===== dashboard/src/components/TimelineChart.tsx =====
cat << 'EOF_TIMELINE' > "$BASE/dashboard/src/components/TimelineChart.tsx"
"use client";

import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { TimelineEntry } from "@/lib/api";

interface Props {
  data: TimelineEntry[];
}

export default function TimelineChart({ data }: Props) {
  if (data.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  const formatted = data.map((d) => ({
    ...d,
    date: new Date(d.date).toLocaleDateString("en-US", {
      month: "short",
      day: "numeric",
    }),
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <AreaChart data={formatted}>
        <defs>
          <linearGradient id="blueGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#3366FF" stopOpacity={0.15} />
            <stop offset="100%" stopColor="#3366FF" stopOpacity={0} />
          </linearGradient>
          <linearGradient id="greenGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#22c55e" stopOpacity={0.1} />
            <stop offset="100%" stopColor="#22c55e" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="#eef1f6" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={{ stroke: "#e2e6ee" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            borderRadius: "12px",
            border: "1px solid #e2e6ee",
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
            fontSize: "12px",
            fontFamily: "Inter",
          }}
        />
        <Area
          type="monotone"
          dataKey="total"
          stroke="#3366FF"
          strokeWidth={2}
          fill="url(#blueGrad)"
          name="Total"
          dot={false}
        />
        <Area
          type="monotone"
          dataKey="interested"
          stroke="#22c55e"
          strokeWidth={1.5}
          fill="url(#greenGrad)"
          name="Interested"
          dot={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
EOF_TIMELINE

# ===== dashboard/src/components/CampaignTable.tsx =====
cat << 'EOF_CAMPAIGN_TABLE' > "$BASE/dashboard/src/components/CampaignTable.tsx"
"use client";

import type { CampaignStats } from "@/lib/api";

interface Props {
  campaigns: CampaignStats[];
}

export default function CampaignTable({ campaigns }: Props) {
  if (campaigns.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No campaign data yet
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-[13px]">
        <thead>
          <tr style={{ borderBottom: "1px solid #e2e6ee" }}>
            <th className="pb-3 pr-4 text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Campaign</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Total</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Interested</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Not Interested</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>OOO</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Unsub</th>
            <th className="pb-3 pr-4 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Info Req</th>
            <th className="pb-3 text-right text-[11px] font-semibold uppercase tracking-wider" style={{ color: "#8a91a5" }}>Rate</th>
          </tr>
        </thead>
        <tbody>
          {campaigns.map((c) => (
            <tr
              key={c.campaign_id}
              className="transition-colors hover:bg-[#f8f9fc]"
              style={{ borderBottom: "1px solid #f0f2f7" }}
            >
              <td className="py-3.5 pr-4 font-medium" style={{ color: "#1a1a2e" }}>
                {c.campaign_name || c.campaign_id}
              </td>
              <td className="py-3.5 pr-4 text-right font-medium" style={{ color: "#5a6176" }}>{c.total}</td>
              <td className="py-3.5 pr-4 text-right font-semibold" style={{ color: "#3366FF" }}>
                {c.interested}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#ef4444" }}>
                {c.not_interested}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#f59e0b" }}>{c.ooo}</td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#94a3b8" }}>
                {c.unsubscribe}
              </td>
              <td className="py-3.5 pr-4 text-right" style={{ color: "#6366f1" }}>
                {c.info_request}
              </td>
              <td className="py-3.5 text-right">
                <span
                  className="inline-flex rounded-lg px-2.5 py-1 text-[11px] font-semibold"
                  style={
                    c.interest_rate >= 20
                      ? { backgroundColor: "#eef2ff", color: "#3366FF" }
                      : c.interest_rate >= 10
                      ? { backgroundColor: "#fffbeb", color: "#d97706" }
                      : { backgroundColor: "#fef2f2", color: "#ef4444" }
                  }
                >
                  {c.interest_rate}%
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
EOF_CAMPAIGN_TABLE

# ===== dashboard/src/components/CampaignBarChart.tsx =====
cat << 'EOF_BARCHART' > "$BASE/dashboard/src/components/CampaignBarChart.tsx"
"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from "recharts";
import type { CampaignStats } from "@/lib/api";

interface Props {
  campaigns: CampaignStats[];
}

export default function CampaignBarChart({ campaigns }: Props) {
  if (campaigns.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-[13px]" style={{ color: "#a5abbe" }}>
        No data yet
      </div>
    );
  }

  const chartData = campaigns.slice(0, 10).map((c) => ({
    name: (c.campaign_name || c.campaign_id).slice(0, 20),
    Interested: c.interested,
    "Not Interested": c.not_interested,
    OOO: c.ooo,
    Unsubscribe: c.unsubscribe,
    "Info Request": c.info_request,
  }));

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={chartData} barCategoryGap="20%">
        <CartesianGrid stroke="#eef1f6" vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={{ stroke: "#e2e6ee" }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11, fill: "#8a91a5", fontFamily: "Inter" }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={{
            borderRadius: "12px",
            border: "1px solid #e2e6ee",
            boxShadow: "0 4px 12px rgba(0,0,0,0.06)",
            fontSize: "12px",
            fontFamily: "Inter",
          }}
        />
        <Legend wrapperStyle={{ fontSize: "12px", fontFamily: "Inter" }} />
        <Bar dataKey="Interested" stackId="a" fill="#3366FF" radius={[0, 0, 0, 0]} />
        <Bar dataKey="Not Interested" stackId="a" fill="#ef4444" />
        <Bar dataKey="OOO" stackId="a" fill="#f59e0b" />
        <Bar dataKey="Unsubscribe" stackId="a" fill="#94a3b8" />
        <Bar dataKey="Info Request" stackId="a" fill="#6366f1" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
EOF_BARCHART

# ===== dashboard/src/components/PeriodFilter.tsx =====
cat << 'EOF_PERIOD' > "$BASE/dashboard/src/components/PeriodFilter.tsx"
"use client";

interface Props {
  value: string;
  onChange: (period: string) => void;
}

const periods = [
  { label: "Today", value: "today" },
  { label: "This Week", value: "week" },
  { label: "This Month", value: "month" },
  { label: "All Time", value: "all" },
];

export default function PeriodFilter({ value, onChange }: Props) {
  return (
    <div
      className="flex gap-0.5 rounded-xl p-1"
      style={{ backgroundColor: "#eef1f6" }}
    >
      {periods.map((p) => (
        <button
          key={p.value}
          onClick={() => onChange(p.value)}
          className="rounded-lg px-3.5 py-1.5 text-[12px] font-medium transition-all"
          style={
            value === p.value
              ? { backgroundColor: "#3366FF", color: "#ffffff" }
              : { color: "#8a91a5" }
          }
          onMouseEnter={(e) => {
            if (value !== p.value) e.currentTarget.style.color = "#1a1a2e";
          }}
          onMouseLeave={(e) => {
            if (value !== p.value) e.currentTarget.style.color = "#8a91a5";
          }}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}
EOF_PERIOD

# ===== dashboard/src/components/Sidebar.tsx =====
cat << 'EOF_SIDEBAR' > "$BASE/dashboard/src/components/Sidebar.tsx"
"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const navItems = [
  {
    href: "/",
    label: "Overview",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6" />
      </svg>
    ),
  },
  {
    href: "/campaigns",
    label: "Campaigns",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
      </svg>
    ),
  },
  {
    href: "/replies",
    label: "Replies",
    icon: (
      <svg className="h-[18px] w-[18px]" fill="none" stroke="currentColor" strokeWidth={1.8} viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
      </svg>
    ),
  },
];

export default function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="fixed left-0 top-0 flex h-screen w-60 flex-col bg-white" style={{ borderRight: "1px solid #e2e6ee" }}>
      <div className="px-6 py-6">
        <h1 className="text-[15px] font-semibold tracking-tight" style={{ color: "#1a1a2e" }}>
          Inbox Manager
        </h1>
        <p className="mt-0.5 text-[11px] font-medium uppercase tracking-wide" style={{ color: "#9ca3b4" }}>
          AI-Powered
        </p>
      </div>

      <nav className="flex-1 px-3 pt-2">
        <p className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest" style={{ color: "#b0b7c8" }}>
          Menu
        </p>
        {navItems.map((item) => {
          const isActive = item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);

          return (
            <Link
              key={item.href}
              href={item.href}
              className="mb-0.5 flex items-center gap-3 rounded-xl px-3 py-2.5 text-[13px] font-medium transition-all"
              style={
                isActive
                  ? { color: "#3366FF", backgroundColor: "#f0f4ff" }
                  : { color: "#5a6176" }
              }
              onMouseEnter={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "#f5f7fa";
              }}
              onMouseLeave={(e) => {
                if (!isActive) e.currentTarget.style.backgroundColor = "transparent";
              }}
            >
              {item.icon}
              {item.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-6 py-5" style={{ borderTop: "1px solid #e2e6ee" }}>
        <p className="text-[11px] font-medium" style={{ color: "#b0b7c8" }}>v1.0 &middot; Powered by AI</p>
      </div>
    </aside>
  );
}
EOF_SIDEBAR

# ===== dashboard/src/lib/api.ts =====
cat << 'EOF_API_TS' > "$BASE/dashboard/src/lib/api.ts"
const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function fetchAPI<T>(endpoint: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`);
  }
  return res.json();
}

// Types
export interface StatsOverview {
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
  wrong_person: number;
  dnc: number;
  pending_approval: number;
  sent: number;
  avg_response_time_minutes: number | null;
  approval_rate: number | null;
}

export interface CampaignStats {
  campaign_id: string;
  campaign_name: string;
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
  wrong_person: number;
  dnc: number;
  interest_rate: number;
}

export interface TimelineEntry {
  date: string;
  total: number;
  interested: number;
  not_interested: number;
  ooo: number;
  unsubscribe: number;
  info_request: number;
}

export interface ResponseTimes {
  avg_approval_time_minutes: number | null;
  avg_send_time_minutes: number | null;
  total_sent: number;
}

export interface FollowUpStats {
  total: number;
  sent: number;
  pending: number;
  by_sequence: Record<string, { total: number; sent: number }>;
}

export interface ReplyItem {
  id: number;
  lead_email: string;
  campaign_name: string;
  category: string;
  status: string;
  reply_body: string;
  draft_response: string;
  received_at: string;
  sent_at: string | null;
}

export interface RepliesResponse {
  replies: ReplyItem[];
  total: number;
  page: number;
  per_page: number;
  pages: number;
}

// API functions
export function getStatsOverview(period = "all"): Promise<StatsOverview> {
  return fetchAPI(`/api/stats/overview?period=${period}`);
}

export function getCampaignStats(period = "all"): Promise<{ campaigns: CampaignStats[] }> {
  return fetchAPI(`/api/stats/campaigns?period=${period}`);
}

export function getTimeline(days = 30): Promise<{ timeline: TimelineEntry[] }> {
  return fetchAPI(`/api/stats/timeline?days=${days}`);
}

export function getResponseTimes(): Promise<ResponseTimes> {
  return fetchAPI("/api/stats/response-times");
}

export function getFollowUpStats(): Promise<FollowUpStats> {
  return fetchAPI("/api/stats/followups");
}

export function getReplies(
  page = 1,
  category?: string,
  status?: string
): Promise<RepliesResponse> {
  const params = new URLSearchParams({ page: String(page) });
  if (category) params.set("category", category);
  if (status) params.set("status", status);
  return fetchAPI(`/api/replies?${params}`);
}
EOF_API_TS

# ===== n8n-workflows/1-slack-notification.json =====
cat << 'EOF_N8N_1' > "$BASE/n8n-workflows/1-slack-notification.json"
{
  "name": "1 - Slack Notification",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "slack-notify",
        "responseMode": "onReceived",
        "responseData": "allEntries"
      },
      "name": "Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [250, 300]
    },
    {
      "parameters": {
        "conditions": {
          "string": [
            {
              "value1": "={{ $json.status }}",
              "operation": "equals",
              "value2": "pending_approval"
            }
          ]
        }
      },
      "name": "Needs Approval?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [450, 300]
    },
    {
      "parameters": {
        "channel": "#inbox-manager",
        "text": "",
        "blocksUi": {
          "blocksValues": [
            {
              "type": "section",
              "textUi": {
                "text": "*New Reply from {{ $json.lead_email }}*\n*Campaign:* {{ $json.campaign_name }}\n*Category:* {{ $json.category }}\n*Received:* {{ $json.received_at }}"
              }
            },
            {
              "type": "section",
              "textUi": {
                "text": "*Their Reply:*\n> {{ $json.reply_body }}"
              }
            },
            {
              "type": "section",
              "textUi": {
                "text": "*AI Draft Response:*\n```{{ $json.draft_response }}```"
              }
            },
            {
              "type": "actions",
              "elementsUi": {
                "elementsValues": [
                  {
                    "type": "button",
                    "text": "Approve & Send",
                    "style": "primary",
                    "actionId": "approve_{{ $json.reply_id }}"
                  },
                  {
                    "type": "button",
                    "text": "Reject",
                    "style": "danger",
                    "actionId": "reject_{{ $json.reply_id }}"
                  }
                ]
              }
            }
          ]
        }
      },
      "name": "Send to Slack",
      "type": "n8n-nodes-base.slack",
      "typeVersion": 2,
      "position": [650, 250],
      "credentials": {
        "slackApi": {
          "id": "CONFIGURE_ME",
          "name": "Slack Account"
        }
      }
    },
    {
      "parameters": {
        "channel": "#inbox-manager",
        "text": "Auto-handled reply from {{ $json.lead_email }} ({{ $json.category }}) - Campaign: {{ $json.campaign_name }}"
      },
      "name": "Log Auto-Handled",
      "type": "n8n-nodes-base.slack",
      "typeVersion": 2,
      "position": [650, 450],
      "credentials": {
        "slackApi": {
          "id": "CONFIGURE_ME",
          "name": "Slack Account"
        }
      }
    }
  ],
  "connections": {
    "Webhook": {
      "main": [
        [{ "node": "Needs Approval?", "type": "main", "index": 0 }]
      ]
    },
    "Needs Approval?": {
      "main": [
        [{ "node": "Send to Slack", "type": "main", "index": 0 }],
        [{ "node": "Log Auto-Handled", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1"
  }
}
EOF_N8N_1

# ===== n8n-workflows/2-approval-handler.json =====
cat << 'EOF_N8N_2' > "$BASE/n8n-workflows/2-approval-handler.json"
{
  "name": "2 - Slack Approval Handler",
  "nodes": [
    {
      "parameters": {
        "httpMethod": "POST",
        "path": "slack-interaction",
        "responseMode": "onReceived"
      },
      "name": "Slack Interaction Webhook",
      "type": "n8n-nodes-base.webhook",
      "typeVersion": 1,
      "position": [250, 300],
      "notes": "Configure Slack app Interactivity URL to point here: http://YOUR_N8N_URL/webhook/slack-interaction"
    },
    {
      "parameters": {
        "values": {
          "string": [
            {
              "name": "action_id",
              "value": "={{ $json.body.actions[0].action_id }}"
            },
            {
              "name": "action_type",
              "value": "={{ $json.body.actions[0].action_id.split('_')[0] }}"
            },
            {
              "name": "reply_id",
              "value": "={{ $json.body.actions[0].action_id.split('_')[1] }}"
            },
            {
              "name": "user",
              "value": "={{ $json.body.user.name }}"
            }
          ]
        }
      },
      "name": "Extract Action",
      "type": "n8n-nodes-base.set",
      "typeVersion": 1,
      "position": [450, 300]
    },
    {
      "parameters": {
        "conditions": {
          "string": [
            {
              "value1": "={{ $json.action_type }}",
              "operation": "equals",
              "value2": "approve"
            }
          ]
        }
      },
      "name": "Approve or Reject?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [650, 300]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://backend:8888/api/send-reply",
        "jsonParameters": true,
        "body": "={{ JSON.stringify({ reply_id: parseInt($json.reply_id), approved_by: $json.user }) }}"
      },
      "name": "Send Reply via Backend",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 3,
      "position": [850, 200]
    },
    {
      "parameters": {
        "method": "PATCH",
        "url": "http://backend:8888/api/replies/{{ $json.reply_id }}?status=rejected"
      },
      "name": "Reject Reply",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 3,
      "position": [850, 400]
    },
    {
      "parameters": {
        "operation": "append",
        "sheetId": "CONFIGURE_YOUR_SHEET_ID",
        "range": "Sheet1",
        "columns": "Timestamp,Lead Email,Campaign,Category,Response,Status,Approved By",
        "values": "={{ new Date().toISOString() }},={{ $node['Extract Action'].json.lead_email || '' }},={{ $json.campaign_name || '' }},={{ $json.category || '' }},={{ $json.draft_response || '' }},=Sent,={{ $json.user }}"
      },
      "name": "Log to Google Sheets",
      "type": "n8n-nodes-base.googleSheets",
      "typeVersion": 4,
      "position": [1050, 200],
      "credentials": {
        "googleSheetsOAuth2Api": {
          "id": "CONFIGURE_ME",
          "name": "Google Sheets Account"
        }
      }
    }
  ],
  "connections": {
    "Slack Interaction Webhook": {
      "main": [
        [{ "node": "Extract Action", "type": "main", "index": 0 }]
      ]
    },
    "Extract Action": {
      "main": [
        [{ "node": "Approve or Reject?", "type": "main", "index": 0 }]
      ]
    },
    "Approve or Reject?": {
      "main": [
        [{ "node": "Send Reply via Backend", "type": "main", "index": 0 }],
        [{ "node": "Reject Reply", "type": "main", "index": 0 }]
      ]
    },
    "Send Reply via Backend": {
      "main": [
        [{ "node": "Log to Google Sheets", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1"
  }
}
EOF_N8N_2

# ===== n8n-workflows/3-followup-cron.json =====
cat << 'EOF_N8N_3' > "$BASE/n8n-workflows/3-followup-cron.json"
{
  "name": "3 - Follow-Up Cron",
  "nodes": [
    {
      "parameters": {
        "rule": {
          "interval": [
            {
              "triggerAtHour": 9,
              "triggerAtMinute": 0
            },
            {
              "triggerAtHour": 13,
              "triggerAtMinute": 0
            },
            {
              "triggerAtHour": 17,
              "triggerAtMinute": 0
            }
          ]
        }
      },
      "name": "Cron Trigger",
      "type": "n8n-nodes-base.scheduleTrigger",
      "typeVersion": 1,
      "position": [250, 300],
      "notes": "Runs at 9am, 1pm, 5pm daily"
    },
    {
      "parameters": {
        "url": "http://backend:8888/api/pending-followups",
        "method": "GET"
      },
      "name": "Get Pending Follow-Ups",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 3,
      "position": [450, 300]
    },
    {
      "parameters": {
        "conditions": {
          "number": [
            {
              "value1": "={{ $json.count }}",
              "operation": "greaterThan",
              "value2": 0
            }
          ]
        }
      },
      "name": "Any Follow-Ups?",
      "type": "n8n-nodes-base.if",
      "typeVersion": 1,
      "position": [650, 300]
    },
    {
      "parameters": {
        "fieldToSplitOut": "followups"
      },
      "name": "Split Items",
      "type": "n8n-nodes-base.splitOut",
      "typeVersion": 1,
      "position": [850, 250]
    },
    {
      "parameters": {
        "method": "POST",
        "url": "http://backend:8888/api/generate-followup",
        "jsonParameters": true,
        "body": "={{ JSON.stringify({ reply_id: $json.reply_id }) }}"
      },
      "name": "Generate Follow-Up",
      "type": "n8n-nodes-base.httpRequest",
      "typeVersion": 3,
      "position": [1050, 250]
    },
    {
      "parameters": {
        "channel": "#inbox-manager",
        "text": "",
        "blocksUi": {
          "blocksValues": [
            {
              "type": "section",
              "textUi": {
                "text": "*Follow-Up #{{ $json.sequence_num }} for {{ $json.lead_email }}*\n*Campaign:* {{ $json.campaign_name }}\n*Day Window:* {{ $json.day_window }} days"
              }
            },
            {
              "type": "section",
              "textUi": {
                "text": "*Follow-Up Message:*\n```{{ $json.follow_up_body }}```"
              }
            },
            {
              "type": "actions",
              "elementsUi": {
                "elementsValues": [
                  {
                    "type": "button",
                    "text": "Send Follow-Up",
                    "style": "primary",
                    "actionId": "approve_{{ $json.reply_id }}"
                  },
                  {
                    "type": "button",
                    "text": "Skip",
                    "style": "danger",
                    "actionId": "reject_{{ $json.reply_id }}"
                  }
                ]
              }
            }
          ]
        }
      },
      "name": "Send Follow-Up to Slack",
      "type": "n8n-nodes-base.slack",
      "typeVersion": 2,
      "position": [1250, 250],
      "credentials": {
        "slackApi": {
          "id": "CONFIGURE_ME",
          "name": "Slack Account"
        }
      }
    }
  ],
  "connections": {
    "Cron Trigger": {
      "main": [
        [{ "node": "Get Pending Follow-Ups", "type": "main", "index": 0 }]
      ]
    },
    "Get Pending Follow-Ups": {
      "main": [
        [{ "node": "Any Follow-Ups?", "type": "main", "index": 0 }]
      ]
    },
    "Any Follow-Ups?": {
      "main": [
        [{ "node": "Split Items", "type": "main", "index": 0 }],
        []
      ]
    },
    "Split Items": {
      "main": [
        [{ "node": "Generate Follow-Up", "type": "main", "index": 0 }]
      ]
    },
    "Generate Follow-Up": {
      "main": [
        [{ "node": "Send Follow-Up to Slack", "type": "main", "index": 0 }]
      ]
    }
  },
  "settings": {
    "executionOrder": "v1"
  }
}
EOF_N8N_3

echo "  All project files written."

# -------------------------------------------------------------------
# 3. Install docker-compose-plugin if needed
# -------------------------------------------------------------------
echo "[3/7] Checking Docker Compose..."
if ! docker compose version &>/dev/null; then
  echo "  Installing docker-compose-plugin..."
  apt-get update -qq && apt-get install -y -qq docker-compose-plugin
else
  echo "  Docker Compose already installed: $(docker compose version --short)"
fi

# -------------------------------------------------------------------
# 4. Open firewall ports
# -------------------------------------------------------------------
echo "[4/7] Opening firewall ports 8080, 8888, 5678..."
if command -v ufw &>/dev/null; then
  ufw allow 8080/tcp >/dev/null 2>&1 || true
  ufw allow 8888/tcp >/dev/null 2>&1 || true
  ufw allow 5678/tcp >/dev/null 2>&1 || true
  echo "  UFW rules added."
else
  echo "  UFW not found — skipping (ensure ports are open in your cloud firewall)."
fi

# -------------------------------------------------------------------
# 5. Build containers
# -------------------------------------------------------------------
echo "[5/7] Building Docker images (this may take a few minutes)..."
cd "$BASE"
docker compose -f docker-compose.prod.yml build

# -------------------------------------------------------------------
# 6. Start containers
# -------------------------------------------------------------------
echo "[6/7] Starting services..."
docker compose -f docker-compose.prod.yml up -d

# -------------------------------------------------------------------
# 7. Verify
# -------------------------------------------------------------------
echo "[7/7] Waiting for services to come up..."
sleep 10

echo ""
echo "=============================================="
echo "  Container status:"
echo "=============================================="
docker compose -f docker-compose.prod.yml ps

echo ""
echo "  Checking health endpoint..."
for i in 1 2 3 4 5; do
  if curl -sf http://localhost:8888/health >/dev/null 2>&1; then
    echo "  Backend is UP: $(curl -s http://localhost:8888/health)"
    break
  fi
  echo "  Attempt $i/5 — waiting..."
  sleep 5
done

echo ""
echo "=============================================="
echo "  Deployment complete!"
echo "=============================================="
echo ""
echo "  Dashboard:  http://$(grep VPS_IP "$BASE/.env" | cut -d= -f2):8080"
echo "  Backend:    http://$(grep VPS_IP "$BASE/.env" | cut -d= -f2):8888"
echo "  n8n:        http://$(grep VPS_IP "$BASE/.env" | cut -d= -f2):5678"
echo "  Health:     http://$(grep VPS_IP "$BASE/.env" | cut -d= -f2):8888/health"
echo ""
echo "  n8n login:  admin / InboxMgr2026!"
echo ""
