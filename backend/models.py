from datetime import datetime
from typing import Optional

from sqlmodel import Field, Relationship, SQLModel


class AppSettings(SQLModel, table=True):
    __tablename__ = "app_settings"

    id: int = Field(default=1, primary_key=True)
    approval_mode: str = "human"  # "human" or "automated"


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
    eaccount: str = ""  # sending email account from Instantly
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


# ---------------------------------------------------------------------------
# LinkedIn (HeyReach) models
# ---------------------------------------------------------------------------

class LinkedInCampaign(SQLModel, table=True):
    __tablename__ = "linkedin_campaigns"

    id: Optional[int] = Field(default=None, primary_key=True)
    heyreach_campaign_id: str = Field(index=True, unique=True)
    name: str
    status: str = "unknown"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    conversations: list["LinkedInConversation"] = Relationship(back_populates="campaign")


class LinkedInConversation(SQLModel, table=True):
    __tablename__ = "linkedin_conversations"

    id: Optional[int] = Field(default=None, primary_key=True)
    heyreach_conversation_id: str = Field(index=True, unique=True)
    account_id: str = ""
    campaign_id: Optional[int] = Field(default=None, foreign_key="linkedin_campaigns.id", index=True)
    heyreach_campaign_id: str = ""
    lead_name: str = ""
    lead_linkedin_url: str = ""
    lead_title: str = ""
    lead_company: str = ""
    last_message: str = ""
    category: str = ""
    draft_response: str = ""
    status: str = "pending_classification"
    created_at: datetime = Field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None

    campaign: Optional[LinkedInCampaign] = Relationship(back_populates="conversations")
