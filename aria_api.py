# aria_api.py
# ARIA Local API — receives emails from Power Automate, analyzes with Claude

import anthropic
import sqlite3
import json
import os
from datetime import datetime
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

app = FastAPI(title="ARIA Email Agent", version="1.0")

DB_PATH = r"C:\Users\MXDELACEGA\OneDrive - NESTLE\GitHub\ARIA-AI-Agent\aria.db"

client = anthropic.Anthropic(
    api_key=os.environ.get("ANTHROPIC_API_KEY")
)

ARIA_SYSTEM_PROMPT = """
You are ARIA, an expert AI email analyst for Gabriela De La Cerda,
TPRM Security Annex Lead at Nestlé Global IT Security & Compliance.

Gabriela's context:
- Manages vendor security assessments and Security Annex reviews globally
- Leads an 8-person team across AMS, LATAM, EUR, AFRICA, AOA regions
- Handles third-party risk escalations, contract negotiations
- Receives 80+ emails daily, needs intelligent triage
- Tone: professional, direct, warm, concise

Analyze each email deeply — understand context, intent, urgency.
Be intelligent, not keyword-based. A polite email can still be a 5 
if it contains a breach. URGENT in subject might be a 2 if it's sales.

Respond ONLY with raw valid JSON — no markdown, no preamble:

{
"category": "VENDOR_SECURITY|TEAM_MANAGEMENT|ESCALATION|MEETING_REQUEST|FYI_ONLY|NEWSLETTER|ADMIN|LEGAL|PROCUREMENT|FOLLOW_UP_NEEDED|SPAM", 
"urgency": 1-5, "summary": "2 sentences max — what is this and why does it matter to Gabriela",
"suggested_action": "REPLY_NOW|DELEGATE|ARCHIVE|SCHEDULE|FOLLOW_UP|DELETE", 
"delegate_to": "name or role or null",
"draft_reply": "complete reply in Gabriela's voice, signed: Gabriela | TPRM Security Annex Lead | Nestlé Global IT — or null",
"follow_up_date": "YYYY-MM-DD or null",
"key_entities": ["vendor names", "people", "systems", "topics"],
"requires_gabriela": true or false,
"reasoning": "1 sentence on why this urgency and action"
}

Urgency:
5 = breach, incident, critical, immediate legal/compliance risk
4 = overdue, today deadline, escalation, non-compliance
3 = needs review, input, vendor follow-up, team decision
2 = FYI, informational, low priority
1 = newsletters, auto-notifications, digests
"""

# ─────────────────────────────────────────────────
# MODELS
# ─────────────────────────────────────────────────
class EmailPayload(BaseModel):
    sender: str
    subject: str
    body: str
    received_at: str
    thread_id: str = ""
    message_id: str = ""

class StatusUpdate(BaseModel):
    email_id: int
    new_status: str
    notes: str = ""

# ─────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────
def save_to_db(data: dict) -> int:
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

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

    email_id = cursor.lastrowid or 0

    if data.get("FollowUpDate"):
        cursor.execute(
            "INSERT INTO ARIA_FollowUps (EmailID, FollowUpDate) VALUES (?,?)",
            (email_id, data["FollowUpDate"])
        )

    cursor.execute(
        "INSERT INTO ARIA_AuditLog (EmailID, Action, NewStatus) VALUES (?,?,?)",
        (email_id, "CREATED", "PENDING")
    )

    conn.commit()
    conn.close()
    return email_id

# ─────────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────────
@app.get("/")
def health_check():
    return {"status": "ARIA is running", "time": datetime.now().isoformat()}

@app.post("/analyze")
async def analyze_email(email: EmailPayload):
    try:
        prompt = f"""Analyze this email for Gabriela:

FROM: {email.sender}
SUBJECT: {email.subject}
RECEIVED: {email.received_at}
BODY:
{email.body}

Return only the JSON analysis."""

        message = client.messages.create(
            model="claude-opus-4-6",
            max_tokens=1500,
            system=ARIA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        # Extract text from the first content block
        text_content = None
        for block in message.content:
            if block.type == "text":
                text_content = block.text
                break
        
        if not text_content:
            raise ValueError("No text content in Claude response")
        
        raw = text_content.strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        result = json.loads(raw)

        data = {
            "ThreadID":         email.thread_id or f"PA-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            "Sender":           email.sender,
            "Subject":          email.subject,
            "BodyPreview":      email.body[:500],
            "ReceivedAt":       email.received_at,
            "Category":         result.get("category", "ADMIN"),
            "Urgency":          int(result.get("urgency", 2)),
            "Summary":          result.get("summary", ""),
            "SuggestedAction":  result.get("suggested_action", "REPLY_NOW"),
            "DelegateTo":       result.get("delegate_to"),
            "DraftReply":       result.get("draft_reply"),
            "FollowUpDate":     result.get("follow_up_date"),
            "KeyEntities":      json.dumps(result.get("key_entities", [])),
            "RequiresGabriela": 1 if result.get("requires_gabriela") else 0,
            "Status":           "PENDING"
        }

        email_id = save_to_db(data)

        if email_id == -1:
            return {"status": "duplicate", "message": "Email already exists"}

        return {
            "status":    "success",
            "email_id":  email_id,
            "category":  data["Category"],
            "urgency":   data["Urgency"],
            "action":    data["SuggestedAction"],
            "summary":   data["Summary"]
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Claude returned invalid JSON")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/status")
async def update_status(update: StatusUpdate):
    try:
        conn = sqlite3.connect(DB_PATH)
        old = conn.execute(
            "SELECT Status FROM ARIA_Emails WHERE EmailID=?",
            (update.email_id,)).fetchone()
        old_status = old[0] if old else None

        conn.execute(
            "UPDATE ARIA_Emails SET Status=?, StatusUpdatedAt=?, Notes=? WHERE EmailID=?",
            (update.new_status, datetime.now().isoformat(),
            update.notes, update.email_id))

        conn.execute(
            "INSERT INTO ARIA_AuditLog (EmailID, Action, OldStatus, NewStatus) VALUES (?,?,?,?)",
            (update.email_id, "STATUS_CHANGE", old_status, update.new_status))

        conn.commit()
        conn.close()
        return {"status": "success", "email_id": update.email_id,
                "new_status": update.new_status}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/pending")
async def get_pending():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    rows = cursor.execute("""
        SELECT EmailID, Sender, Subject, Category, Urgency,
        Summary, SuggestedAction, RequiresGabriela
        FROM ARIA_Emails
        WHERE Status = 'PENDING'
        ORDER BY Urgency DESC, ReceivedAt DESC
    """).fetchall()
    conn.close()
    return {"count": len(rows), "emails": [
        {"id": r[0], "sender": r[1], "subject": r[2],
        "category": r[3], "urgency": r[4], "summary": r[5],
        "action": r[6], "requires_gabriela": bool(r[7])}
        for r in rows
    ]}

# ─────────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("🚀 ARIA API starting on http://localhost:8080")
    print("   Power Automate endpoint: http://localhost:8080/analyze")
    print("   Health check: http://localhost:8080/")
    uvicorn.run(app, host="127.0.0.1", port=8080)