# aria_brain.py
# ARIA — Automated Reply & Inbox Agent
# Brain powered by Claude AI (Anthropic)

import anthropic
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = r"C:\Users\MXDELACEGA\OneDrive - NESTLE\GitHub\ARIA-AI-Agent\aria.db"

# ─────────────────────────────────────────────────
# CLAUDE CLIENT
# ─────────────────────────────────────────────────
client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

# ─────────────────────────────────────────────────
# ARIA SYSTEM PROMPT
# ─────────────────────────────────────────────────
ARIA_SYSTEM_PROMPT = """
You are ARIA, an expert AI email analyst for Gabriela De La Cerda,
TPRM Security Annex Lead at Nestlé Global IT Security & Compliance.

Gabriela's context:
- Manages vendor security assessments and Security Annex reviews globally
- Leads an 8-person team across AMS, LATAM, EUR, AFRICA, AOA regions
- Handles third-party risk escalations, contract negotiations
- Coordinates with legal, procurement, and IT teams
- Has completed 600+ vendor security implementations
- Works under high volume — receives 80+ emails daily
- Tone: professional, direct, warm, concise

Your job is to analyze each email deeply — understand context, intent, 
urgency, relationships, and what action truly serves Gabriela best.

You must respond ONLY with a valid JSON object. No preamble, no explanation,
no markdown — just raw JSON.

Return exactly this structure:
{
  "category": "one of: VENDOR_SECURITY | TEAM_MANAGEMENT | ESCALATION | MEETING_REQUEST | FYI_ONLY | NEWSLETTER | ADMIN | LEGAL | PROCUREMENT | FOLLOW_UP_NEEDED | SPAM",
  "urgency": "integer 1-5",
  "summary": "2 sentences max — plain English, tell Gabriela exactly what this is about and why it matters",
  "suggested_action": "one of: REPLY_NOW | DELEGATE | ARCHIVE | SCHEDULE | FOLLOW_UP | DELETE",
  "delegate_to": "specific name or role if someone on her team can handle this, otherwise null",
  "draft_reply": "complete professional reply written in Gabriela's voice — direct, warm, concise. Sign off: Gabriela | TPRM Security Annex Lead | Nestlé Global IT. Write in English unless original is Spanish. null if no reply needed.",
  "follow_up_date": "YYYY-MM-DD if this needs a follow-up, otherwise null",
  "key_entities": ["array", "of", "vendor names", "people", "topics", "systems mentioned"],
  "requires_gabriela": true or false,
  "reasoning": "1 sentence explaining why you assigned this urgency and action"
}

Urgency guide:
5 = Security breach, incident, critical compliance violation, immediate legal risk
4 = Overdue items, today deadlines, escalations, non-compliance flags
3 = Needs Gabriela's review or input, vendor follow-ups, team decisions
2 = FYI updates, informational, low priority requests
1 = Newsletters, auto-notifications, digests, no-reply senders

Be intelligent — read between the lines. A politely worded email can still
be a 5 if it contains a breach report. A subject saying URGENT might be 
a 2 if it's just a sales email. Use judgment, not keywords.
"""

# ─────────────────────────────────────────────────
# CORE ANALYSIS FUNCTION
# ─────────────────────────────────────────────────
def analyze_email(sender: str, subject: str, body: str,
                  received_at: str, thread_id: str) -> dict:
    
    prompt = f"""Analyze this email for Gabriela:

FROM: {sender}
SUBJECT: {subject}
RECEIVED: {received_at}
BODY:
{body}

Return only the JSON analysis."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=1500,
        system=ARIA_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()
    
    # Clean any accidental markdown
    raw = raw.replace("```json", "").replace("```", "").strip()
    result = json.loads(raw)

    return {
        "ThreadID":          thread_id,
        "Sender":            sender,
        "Subject":           subject,
        "BodyPreview":       body[:500],
        "ReceivedAt":        received_at,
        "Category":          result.get("category", "ADMIN"),
        "Urgency":           int(result.get("urgency", 2)),
        "Summary":           result.get("summary", ""),
        "SuggestedAction":   result.get("suggested_action", "REPLY_NOW"),
        "DelegateTo":        result.get("delegate_to"),
        "DraftReply":        result.get("draft_reply"),
        "FollowUpDate":      result.get("follow_up_date"),
        "KeyEntities":       json.dumps(result.get("key_entities", [])),
        "RequiresGabriela":  1 if result.get("requires_gabriela") else 0,
        "Status":            "PENDING",
        "Reasoning":         result.get("reasoning", "")
    }

# ─────────────────────────────────────────────────
# SAVE TO DATABASE
# ─────────────────────────────────────────────────
def save_email(data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Skip duplicates
    existing = cursor.execute(
        "SELECT EmailID FROM ARIA_Emails WHERE Subject=? AND Sender=?",
        (data["Subject"], data["Sender"])
    ).fetchone()

    if existing:
        conn.close()
        return -1

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
        cursor.execute(
            "INSERT INTO ARIA_FollowUps (EmailID, FollowUpDate) VALUES (?,?)",
            (email_id, data["FollowUpDate"])
        )

    # Audit log
    cursor.execute(
        "INSERT INTO ARIA_AuditLog (EmailID, Action, NewStatus) VALUES (?,?,?)",
        (email_id, "CREATED", "PENDING")
    )

    conn.commit()
    conn.close()
    return email_id

# ─────────────────────────────────────────────────
# PROCESS FROM FILE (aria_response.txt)
# ─────────────────────────────────────────────────
def process_from_file():
    """
    Reads aria_response.txt — each email block separated by ---
    Format per block:
    FROM: sender@email.com
    SUBJECT: Subject line here
    RECEIVED: 2026-02-23T10:00:00
    BODY:
    Email body text here...
    """
    response_file = r"C:\Users\MXDELACEGA\OneDrive - NESTLE\GitHub\ARIA-AI-Agent\aria_inbox.txt"

    if not os.path.exists(response_file):
        print(f"❌ File not found: {response_file}")
        print("   Create aria_inbox.txt with your emails and run again.")
        return

    with open(response_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Split into individual email blocks
    blocks = [b.strip() for b in content.split("---") if b.strip()]
    print(f"\n🧠 ARIA Brain — Processing {len(blocks)} emails with Claude AI\n" + "="*55)

    saved = 0
    skipped = 0

    for i, block in enumerate(blocks, 1):
        try:
            lines = block.split("\n")
            sender   = ""
            subject  = ""
            received = datetime.now().isoformat()
            body     = ""
            in_body  = False

            for line in lines:
                if line.startswith("FROM:"):
                    sender = line.replace("FROM:", "").strip()
                elif line.startswith("SUBJECT:"):
                    subject = line.replace("SUBJECT:", "").strip()
                elif line.startswith("RECEIVED:"):
                    received = line.replace("RECEIVED:", "").strip()
                elif line.startswith("BODY:"):
                    in_body = True
                elif in_body:
                    body += line + "\n"

            if not sender or not subject:
                print(f"   ⚠️  Block {i} skipped — missing FROM or SUBJECT")
                continue

            print(f"   📧 [{i}/{len(blocks)}] Analyzing: {subject[:50]}...")

            result = analyze_email(
                sender=sender,
                subject=subject,
                body=body.strip(),
                received_at=received,
                thread_id=f"ARIA-{datetime.now().strftime('%Y%m%d%H%M%S')}-{i}"
            )

            email_id = save_email(result)

            if email_id == -1:
                print(f"         ↳ ⏭️  Duplicate skipped")
                skipped += 1
            else:
                u = result['Urgency']
                icon = "🔴" if u>=5 else "🟠" if u>=4 else "🟡" if u>=3 else "🔵"
                print(f"         ↳ {icon} {result['Category']} | Urgency {u}/5 | {result['SuggestedAction']}")
                print(f"         ↳ 💬 {result['Summary'][:80]}...")
                if result.get('DraftReply'):
                    print(f"         ↳ ✍️  Draft reply generated")
                saved += 1

        except json.JSONDecodeError as e:
            print(f"   ❌ Block {i} — Claude returned invalid JSON: {e}")
        except Exception as e:
            print(f"   ❌ Block {i} — Error: {e}")

    print(f"\n{'='*55}")
    print(f"✅ Complete: {saved} saved, {skipped} duplicates skipped")
    print(f"🚀 Open Streamlit dashboard to review your inbox!")

# ─────────────────────────────────────────────────
# TEST WITH REAL EMAILS
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    process_from_file()
    