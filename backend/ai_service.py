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

IMPORTANT: The email below may contain a quoted thread with multiple messages. You must identify which part is the PROSPECT'S LATEST REPLY and classify ONLY that. Ignore any quoted/forwarded messages from our side (the sender/sales team). Look for quoted text indicators like "On [date] [person] wrote:", ">" prefixes, or "From:" headers to distinguish the prospect's new message from the quoted thread.

Classify the prospect's latest reply into exactly ONE of these categories:

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

DRAFT_RESPONSE_PROMPT = """You are a cold email reply agent for a B2B agency. You STRICTLY follow the playbook below. Do not improvise or add information not in the playbook. If the playbook does not cover the prospect's question, output "Needs Josh's help" as the entire response.

PLAYBOOK (follow this EXACTLY):
{playbook}

CONTEXT:
- Lead email: {lead_email}
- Campaign: {campaign_name}
- Their reply category: {category}
- Their original reply (may contain quoted thread. Focus ONLY on the PROSPECT'S LATEST message. Ignore our previous outreach messages in the quoted thread): {reply_body}
- Sender name for sign-off: {sender_name}

ABSOLUTE RULES (NEVER BREAK THESE):
1. NEVER use em dashes, en dashes, hyphens, or any dash character. Not a single one. Rewrite sentences to avoid them entirely.
2. NEVER say "done for you" in any reply.
3. NEVER say there are no upfront costs.
4. NEVER say "pay on results" or imply commission/performance based payment.
5. NEVER use more than 1 exclamation mark per response. Prefer periods. Count your exclamation marks before outputting. If you have more than 1, replace the extras with periods.
6. Sign off with the sender name: {sender_name}. If sender name is "Unknown", just sign off with "Best," and no name.
7. NEVER ask "what time works for you" or "when are you free" or any variation. Instead, always direct them to book via the link. Say something like "feel free to book here for whatever time works best for you" followed by the booking link.
8. Every response MUST include the booking link https://msg.jkdagency.com/widget/bookings/jkdagencydiscoe as the CTA. No exceptions. Even if the prospect provides a phone number, suggests calling, or shares their own calendar link, always use OUR booking link only. Never use any other calendar or booking URL.
9. When including links from the playbook, paste the FULL URL exactly as written. Never shorten, modify, or break URLs.
9. LINE BREAKS ARE CRITICAL. Every single sentence or distinct thought MUST be separated by a blank line. Do NOT put two sentences in the same paragraph. A greeting is one paragraph. Each sentence is its own paragraph. The CTA with booking link is its own paragraph. The sign off is its own paragraph. If your output has any paragraph with more than 2 sentences, split it.
10. Keep it casual, conversational, brief. 2-4 short paragraphs max.
11. When sharing case studies or videos, pick the 1-2 most relevant to the prospect's niche. Never dump multiple links.
12. SPACING: Use exactly one blank line between each paragraph. No double blank lines. No trailing spaces. Consistent spacing throughout. Format must be:

Greeting line

Paragraph 1

Paragraph 2

Sign off,
Name

Write ONLY the email body text. No subject line. No explanations."""

REVISE_DRAFT_PROMPT = """You are a B2B cold email expert revising a draft response based on user feedback.

MESSAGING PLAYBOOK:
{playbook}

CONTEXT:
- Lead email: {lead_email}
- Campaign: {campaign_name}
- Their reply category: {category}
- Their original reply: {reply_body}
- Current draft response: {current_draft}

USER FEEDBACK:
{feedback}

Revise the draft incorporating the feedback. Keep the same general intent but adjust based on what the user asked for.

ABSOLUTE RULES (NEVER BREAK):
1. NEVER use em dashes, en dashes, hyphens, or any dash character. Rewrite to avoid them.
2. NEVER say "done for you", no upfront costs claims, no pay on results.
3. Max 1 exclamation mark per response.
4. Proper line breaks between paragraphs. 2-4 short paragraphs.
5. End with a question or CTA.
6. Paste full URLs exactly. Never modify links.
7. Casual, conversational, brief.

Write ONLY the revised email body text. No subject line, no explanations."""

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
        model="gpt-4o",
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
    sender_name: str = "Unknown",
) -> str:
    """Generate a draft response using the messaging playbook."""
    if not client or settings.test_mode:
        return _mock_draft(lead_email, category)

    playbook = _load_file(settings.playbook_path)
    if not playbook:
        playbook = "(No playbook provided - use professional B2B sales best practices)"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": DRAFT_RESPONSE_PROMPT.format(
                    playbook=playbook,
                    lead_email=lead_email,
                    campaign_name=campaign_name,
                    category=category,
                    reply_body=reply_body,
                    sender_name=sender_name,
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
        model="gpt-4o",
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


async def revise_draft(
    reply_body: str,
    lead_email: str,
    campaign_name: str,
    category: str,
    current_draft: str,
    feedback: str,
) -> str:
    """Revise a draft response based on user feedback."""
    if not client or settings.test_mode:
        return f"[Revised based on feedback: '{feedback}'] {current_draft}"

    playbook = _load_file(settings.playbook_path)
    if not playbook:
        playbook = "(No playbook provided - use professional B2B sales best practices)"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": REVISE_DRAFT_PROMPT.format(
                    playbook=playbook,
                    lead_email=lead_email,
                    campaign_name=campaign_name,
                    category=category,
                    reply_body=reply_body,
                    current_draft=current_draft,
                    feedback=feedback,
                ),
            }
        ],
        temperature=0.7,
        max_tokens=300,
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
