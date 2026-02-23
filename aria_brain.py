# aria_brain.py
# ARIA Brain — Email Analysis Engine
# Uses rule-based AI locally, connects to Copilot Studio via Power Automate

import sqlite3
import json
from datetime import datetime, date

DB_PATH = r"C:\Users\MXDELACEGA\OneDrive - NESTLE\GitHub\ARIA-AI-Agent\aria.db"

# ─────────────────────────────────────────────────
# KEYWORD RULES ENGINE
# (Works offline — no API key needed)
# Copilot Studio will replace/enhance this later
# ─────────────────────────────────────────────────

CATEGORY_RULES = {
    "VENDOR_SECURITY": [
        "security annex", "vendor", "supplier", "tprm", "third party",
        "risk assessment", "security review", "questionnaire", "saq",
        "penetration test", "pentest", "iso 27001", "soc2", "soc 2"
    ],
    "ESCALATION": [
        "escalat", "urgent", "critical", "breach", "incident",
        "violation", "non-complian", "overdue", "immediate"
    ],
    "MEETING_REQUEST": [
        "meeting", "call", "invite", "calendar", "schedule",
        "catch up", "sync", "teams call", "zoom"
    ],
    "LEGAL": [
        "contract", "legal", "clause", "gdpr", "privacy",
        "data protection", "dpa", "agreement", "terms"
    ],
    "PROCUREMENT": [
        "purchase", "procurement", "po ", "invoice", "budget",
        "cost", "payment", "sourcing"
    ],
    "TEAM_MANAGEMENT": [
        "team", "my report", "direct report", "performance",
        "leave", "vacation", "pto", "absence"
    ],
    "NEWSLETTER": [
        "unsubscribe", "newsletter", "digest", "weekly update",
        "monthly report", "bulletin", "no-reply", "noreply"
    ],
    "FOLLOW_UP_NEEDED": [
        "follow up", "following up", "reminder", "pending",
        "still waiting", "no response", "chasing"
    ],
    "SPAM": [
        "congratulations you won", "click here", "limited offer",
        "free gift", "act now", "verify your account"
    ],
}

URGENCY_RULES = {
    5: ["breach", "incident", "critical", "immediate action",
        "escalat", "urgent", "asap", "today"],
    4: ["overdue", "deadline", "by end of day", "eod",
        "non-complian", "violation", "pending approval"],
    3: ["follow up", "reminder", "please review",
        "your input", "feedback needed"],
    2: ["fyi", "for your information", "update",
        "newsletter", "digest"],
    1: ["unsubscribe", "no-reply", "automatic", "noreply"],
}

def classify_category(subject: str, body: str) -> str:
    text = (subject + " " + body).lower()
    for category, keywords in CATEGORY_RULES.items():
        if any(kw in text for kw in keywords):
            return category
    return "ADMIN"

def classify_urgency(subject: str, body: str) -> int:
    text = (subject + " " + body).lower()
    for urgency, keywords in URGENCY_RULES.items():
        if any(kw in text for kw in keywords):
            return urgency
    return 2

def suggest_action(category: str, urgency: int) -> str:
    if urgency >= 4:
        return "REPLY_NOW"
    if category in ["NEWSLETTER", "SPAM"]:
        return "ARCHIVE"
    if category == "MEETING_REQUEST":
        return "SCHEDULE"
    if category == "FOLLOW_UP_NEEDED":
        return "FOLLOW_UP"
    if category in ["TEAM_MANAGEMENT"]:
        return "DELEGATE"
    return "REPLY_NOW"

def requires_gabriela(category: str, urgency: int) -> bool:
    if urgency >= 4:
        return True
    if category in ["ESCALATION", "VENDOR_SECURITY", "LEGAL"]:
        return True
    return False

def generate_summary(sender: str, subject: str, body: str) -> str:
    body_short = body[:300] if len(body) > 300 else body
    return f"Email from {sender} regarding '{subject}'. {body_short[:150]}..."

def generate_draft_reply(category: str, sender: str,
                          subject: str, urgency: int) -> str:
    sender_name = sender.split("@")[0].replace(".", " ").title()

    if category == "MEETING_REQUEST":
        return (f"Hi {sender_name},\n\nThank you for reaching out. "
                f"I'd be happy to connect. Please feel free to send "
                f"a calendar invite at your convenience, or let me know "
                f"your preferred time slots.\n\nBest regards,\nGabriela")

    if category == "VENDOR_SECURITY":
        return (f"Hi {sender_name},\n\nThank you for your message regarding "
                f"{subject}. I will review the details and get back to you "
                f"with next steps within 2 business days.\n\n"
                f"Best regards,\nGabriela\nTPRM Security Annex Lead | Nestlé")

    if category == "ESCALATION" or urgency >= 4:
        return (f"Hi {sender_name},\n\nThank you for flagging this. "
                f"I am treating this as a priority and will respond "
                f"with a full update shortly.\n\n"
                f"Best regards,\nGabriela\nTPRM Security Annex Lead | Nestlé")

    if category in ["NEWSLETTER", "SPAM"]:
        return None

    return (f"Hi {sender_name},\n\nThank you for your email. "
            f"I will review and come back to you shortly.\n\n"
            f"Best regards,\nGabriela\nTPRM Security Annex Lead | Nestlé")

def extract_entities(subject: str, body: str) -> str:
    text = (subject + " " + body)
    entities = []
    keywords = ["Nestlé", "TPRM", "Security Annex", "GDPR",
                 "ISO 27001", "SOC2", "ALSEA", "PayPal"]
    for kw in keywords:
        if kw.lower() in text.lower():
            entities.append(kw)
    return json.dumps(entities)

# ─────────────────────────────────────────────────
# MAIN ANALYSIS FUNCTION
# ─────────────────────────────────────────────────

def analyze_email(sender: str, subject: str, body: str,
                  received_at: str, thread_id: str) -> dict:
    category        = classify_category(subject, body)
    urgency         = classify_urgency(subject, body)
    action          = suggest_action(category, urgency)
    needs_gabriela  = requires_gabriela(category, urgency)
    summary         = generate_summary(sender, subject, body)
    draft           = generate_draft_reply(category, sender, subject, urgency)
    entities        = extract_entities(subject, body)

    return {
        "ThreadID":         thread_id,
        "Sender":           sender,
        "Subject":          subject,
        "BodyPreview":      body[:500],
        "ReceivedAt":       received_at,
        "Category":         category,
        "Urgency":          urgency,
        "Summary":          summary,
        "SuggestedAction":  action,
        "DelegateTo":       None,
        "DraftReply":       draft,
        "FollowUpDate":     None,
        "KeyEntities":      entities,
        "RequiresGabriela": 1 if needs_gabriela else 0,
        "Status":           "PENDING"
    }

def save_email(data: dict):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO ARIA_Emails (
            ThreadID, Sender, Subject, BodyPreview, ReceivedAt,
            Category, Urgency, Summary, SuggestedAction,
            DelegateTo, DraftReply, FollowUpDate, KeyEntities,
            RequiresGabriela, Status
        ) VALUES (
            :ThreadID, :Sender, :Subject, :BodyPreview, :ReceivedAt,
            :Category, :Urgency, :Summary, :SuggestedAction,
            :DelegateTo, :DraftReply, :FollowUpDate, :KeyEntities,
            :RequiresGabriela, :Status
        )
    """, data)

    email_id = cursor.lastrowid

    if data.get("FollowUpDate"):
        cursor.execute("""
            INSERT INTO ARIA_FollowUps (EmailID, FollowUpDate)
            VALUES (?, ?)
        """, (email_id, data["FollowUpDate"]))

    conn.commit()
    conn.close()
    return email_id

# ─────────────────────────────────────────────────
# TEST — Run this file directly to verify
# ─────────────────────────────────────────────────

if __name__ == "__main__":
    test_emails = [
        {
            "sender": "vendor.security@supplierco.com",
            "subject": "Security Annex Review Required — Q1 2026",
            "body": "Hi Gabriela, please find attached our updated Security Annex for your review. We need your sign-off before end of month.",
            "received_at": datetime.now().isoformat(),
            "thread_id": "TEST-001"
        },
        {
            "sender": "ceo.office@nestle.com",
            "subject": "URGENT: Data breach incident report needed immediately",
            "body": "Gabriela, we have a critical incident. A vendor has reported a potential data breach affecting Nestlé systems. Immediate escalation required.",
            "received_at": datetime.now().isoformat(),
            "thread_id": "TEST-002"
        },
        {
            "sender": "newsletter@cybersecuritydigest.com",
            "subject": "Your weekly cybersecurity digest is here",
            "body": "This week in cybersecurity: top 10 threats, industry news, and more. Unsubscribe at any time.",
            "received_at": datetime.now().isoformat(),
            "thread_id": "TEST-003"
        }
    ]

    print("\n🧠 ARIA Brain — Test Run\n" + "="*50)
    for email in test_emails:
        result = analyze_email(**email)
        save_email(result)
        print(f"\n📧 {email['subject'][:50]}")
        print(f"   Category : {result['Category']}")
        print(f"   Urgency  : {'🔴' if result['Urgency']==5 else '🟠' if result['Urgency']==4 else '🟡'} {result['Urgency']}/5")
        print(f"   Action   : {result['SuggestedAction']}")
        print(f"   Needs You: {'✅ Yes' if result['RequiresGabriela'] else '❌ No'}")
        print(f"   Draft    : {str(result['DraftReply'])[:60]}...")

    print("\n✅ 3 test emails saved to ARIA database. Brain is working!")