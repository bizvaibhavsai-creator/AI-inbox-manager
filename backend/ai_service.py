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

DRAFT_RESPONSE_PROMPT = """You are a cold email reply agent for a B2B agency. You follow the playbook below closely. Use the playbook's tone, messaging, and guidelines to craft your reply.

IMPORTANT: Only output "Needs Josh's help" if the prospect asks a very specific or unusual question that is genuinely NOT addressed by ANY section of the playbook. For standard cases like interested replies, booking requests, pricing questions, case study requests, guarantee questions, objections, or any topic the playbook has guidance on, you MUST draft a real response. When in doubt, draft a response rather than escalating.

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
10. LINE BREAKS (THIS IS THE MOST IMPORTANT RULE. FOLLOW IT EXACTLY):
- Put EXACTLY ONE blank line (two newlines) between every sentence or thought.
- NEVER put two sentences next to each other in the same paragraph. Every single sentence gets its own paragraph.
- The greeting ("Hi Name,") is alone on its own line, followed by a blank line.
- Each sentence of the body is its own paragraph, separated by blank lines.
- The booking link gets its own line, separated by blank lines above and below.
- The sign off ("Best,") and name are at the end, separated by a blank line from the last sentence.
- BEFORE outputting, scan your response. If ANY paragraph contains more than one sentence (more than one period), you MUST split it. This is non negotiable.
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


# ---------------------------------------------------------------------------
# LinkedIn (HeyReach) AI functions
# ---------------------------------------------------------------------------

LINKEDIN_CATEGORIES = [
    "interested",
    "not_interested",
    "info_request",
    "referral",
    "wrong_person",
    "out_of_office",
    "already_client",
    "outgoing",
]

LINKEDIN_CLASSIFICATION_PROMPT = """You are an expert at classifying B2B LinkedIn message responses.

IMPORTANT: First determine if this message was sent BY the sales rep (outgoing) or BY the prospect (inbound). Clues that it is outgoing/from the sales rep: it pitches a service, mentions booking links, uses phrases like "would you be open to", "happy to share", "feel free to book". If the message is clearly from the sales rep and NOT from the prospect, classify as "outgoing".

If the message IS from the prospect, classify it into exactly ONE of these categories:

- interested: The prospect expresses interest, wants to learn more, asks for a call/meeting, or gives a positive signal. Also includes prospects who propose specific meeting times, share their availability, or ask "when can we talk"
- not_interested: The prospect explicitly declines, says not a fit, or gives a clear negative response
- info_request: The prospect asks for more information, pricing, case studies, or specifics before committing
- referral: The prospect refers you to someone else at their company or externally
- wrong_person: The prospect says they're not the right contact
- out_of_office: Out of office / auto-reply / vacation message
- already_client: The prospect is already a client or working with someone similar
- outgoing: The message is from the sales rep, not the prospect

Respond with ONLY the category name, nothing else.

LinkedIn message:
{message}"""

LINKEDIN_DRAFT_PROMPT = """You are a LinkedIn outreach reply agent. You follow the playbook below closely. Use the playbook's tone, messaging, and guidelines to craft your reply.

IMPORTANT: Only output "Needs Josh's help" if the prospect asks a very specific or unusual question that is genuinely NOT addressed by ANY section of the playbook. For interested replies, booking requests, pricing, objections, or any topic the playbook covers, you MUST draft a real response. When in doubt, draft a response rather than escalating.

PLAYBOOK (follow this EXACTLY):
{playbook}

CONTEXT:
- Lead name: {lead_name}
- Lead title: {lead_title}
- Lead company: {lead_company}
- Campaign: {campaign_name}
- Their reply category: {category}
- Their latest message: {message}
{thread_section}
ABSOLUTE RULES (NEVER BREAK THESE):
1. NEVER use em dashes, en dashes, hyphens, or any dash character. Rewrite sentences to avoid them.
2. Keep it SHORT. LinkedIn messages should be 2-4 sentences max. Never write long paragraphs.
3. Sound natural and conversational, not like a sales pitch.
4. Every sentence must be its own paragraph with a blank line between them.
5. End with a clear next step or question.
6. NEVER use more than 1 exclamation mark.
7. Do not use email-style greetings or sign-offs. LinkedIn messages are casual.
8. Address the prospect's specific questions or concerns. Never give a generic reply that ignores what they said.
9. Always write from an individual perspective using "I" and "me", not "us" and "we" when referring to yourself. Only use "we" when talking about the agency's results generally.

Write ONLY the message text. No explanations."""


async def classify_linkedin_message(message: str) -> str:
    """Classify a LinkedIn message into a category."""
    if not client or settings.test_mode:
        return "interested"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": LINKEDIN_CLASSIFICATION_PROMPT.format(message=message),
            }
        ],
        temperature=0,
        max_tokens=20,
    )
    category = response.choices[0].message.content.strip().lower()
    if category not in LINKEDIN_CATEGORIES:
        return "not_interested"
    # Map "outgoing" to a flag the caller can handle
    return category


async def generate_linkedin_draft(
    message: str,
    lead_name: str,
    lead_title: str,
    lead_company: str,
    campaign_name: str,
    category: str,
    thread_context: str = "",
) -> str:
    """Generate a LinkedIn reply draft using the LinkedIn playbook."""
    if not client or settings.test_mode:
        return f"Hey {lead_name}, thanks for the reply! Would love to connect on a quick call to share more. When works for you?"

    playbook = _load_file(settings.linkedin_playbook_path)
    if not playbook:
        playbook = "(No playbook provided - use professional B2B LinkedIn messaging best practices)"

    thread_section = ""
    if thread_context:
        thread_section = f"\nCONVERSATION THREAD (for context, reply to the prospect's latest message):\n{thread_context}\n"

    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {
                "role": "user",
                "content": LINKEDIN_DRAFT_PROMPT.format(
                    playbook=playbook,
                    lead_name=lead_name,
                    lead_title=lead_title,
                    lead_company=lead_company,
                    campaign_name=campaign_name,
                    category=category,
                    message=message,
                    thread_section=thread_section,
                ),
            }
        ],
        temperature=0.7,
        max_tokens=200,
    )
    return response.choices[0].message.content.strip()
