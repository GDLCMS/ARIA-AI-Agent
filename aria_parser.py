# aria_parser.py
# Parses ARIA agent output into structured data and saves to SQLite

import sqlite3
import re
from datetime import datetime

DB_PATH = r"C:\Users\MXDELACEGA\OneDrive - NESTLE\GitHub\ARIA-AI-Agent\aria.db"

def parse_aria_response(raw_text: str) -> list:
    """
    Parses the structured EMAIL_START...EMAIL_END blocks
    from ARIA's Copilot response into a list of dicts.
    """
    emails = []
    blocks = re.findall(
        r'EMAIL_START(.*?)EMAIL_END',
        raw_text,
        re.DOTALL
    )

    for block in blocks:
        def extract(field):
            pattern = rf'{field}:\s*(.+?)(?=\n[A-Z_]+:|$)'
            match = re.search(pattern, block.strip(), re.DOTALL)
            if match:
                val = match.group(1).strip()
                return None if val.upper() == "NONE" else val
            return None

        # Clean subject — remove URLs
        subject_raw = extract("SUBJECT") or "No Subject"
        subject = re.sub(r'\(https?://\S+\)', '', subject_raw).strip()
        subject = re.sub(r'\[([^\]]+)\]', r'\1', subject).strip()

        # Clean sender — extract just the name
        sender_raw = extract("FROM") or "Unknown"
        sender = re.sub(r'\(https?://\S+\)', '', sender_raw).strip()
        sender = re.sub(r'\[([^\]]+)\]', r'\1', sender).strip()

        urgency_raw = extract("URGENCY")
        try:
            urgency = int(urgency_raw) if urgency_raw else 2
        except:
            urgency = 2

        requires = extract("REQUIRES_GABRIELA")
        requires_flag = 1 if requires and requires.upper() == "YES" else 0

        email_data = {
            "ThreadID":          f"ARIA-{datetime.now().strftime('%Y%m%d%H%M%S')}-{len(emails)}",
            "Sender":            sender,
            "Subject":           subject,
            "BodyPreview":       block.strip()[:500],
            "ReceivedAt":        datetime.now().isoformat(),
            "Category":          extract("CATEGORY") or "ADMIN",
            "Urgency":           urgency,
            "Summary":           extract("SUMMARY") or "",
            "SuggestedAction":   extract("ACTION") or "REPLY_NOW",
            "DelegateTo":        extract("DELEGATE_TO"),
            "DraftReply":        extract("DRAFT_REPLY"),
            "FollowUpDate":      extract("FOLLOW_UP_DATE"),
            "KeyEntities":       "[]",
            "RequiresGabriela":  requires_flag,
            "Status":            "PENDING"
        }
        emails.append(email_data)

    return emails

def save_emails(emails: list) -> int:
    """Save parsed emails to SQLite, skip duplicates by Subject+Sender."""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    saved = 0

    for data in emails:
        # Skip duplicates
        existing = cursor.execute(
            "SELECT EmailID FROM ARIA_Emails WHERE Subject=? AND Sender=?",
            (data["Subject"], data["Sender"])
        ).fetchone()

        if existing:
            continue

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

        if data.get("FollowUpDate"):
            email_id = cursor.lastrowid
            cursor.execute(
                "INSERT INTO ARIA_FollowUps (EmailID, FollowUpDate) VALUES (?,?)",
                (email_id, data["FollowUpDate"])
            )
        saved += 1

    conn.commit()
    conn.close()
    return saved

def process_aria_output(raw_text: str):
    """Full pipeline: parse → save → report."""
    print("\n🧠 ARIA Parser — Processing response...")
    emails = parse_aria_response(raw_text)
    print(f"   Found {len(emails)} email blocks in response")

    if not emails:
        print("   ⚠️ No EMAIL_START/END blocks found. Check ARIA output format.")
        return

    saved = save_emails(emails)
    print(f"   ✅ Saved {saved} new emails to database ({len(emails)-saved} duplicates skipped)")

    print("\n📊 Summary:")
    for e in emails:
        u = e['Urgency']
        icon = "🔴" if u>=5 else "🟠" if u>=4 else "🟡" if u>=3 else "🔵"
        print(f"   {icon} [{e['Category']}] {e['Subject'][:50]}")
        print(f"      Action: {e['SuggestedAction']} | Needs You: {'✅' if e['RequiresGabriela'] else '❌'}")

# ─────────────────────────────────────────────────
# MANUAL MODE — paste ARIA output directly here
# ─────────────────────────────────────────────────
if __name__ == "__main__":
    print("📋 Paste ARIA's full response below.")
    print("   When done, type END on a new line and press Enter:\n")

    lines = []
    while True:
        line = input()
        if line.strip() == "END":
            break
        lines.append(line)

    raw = "\n".join(lines)
    process_aria_output(raw)
    print("\n✅ Done! Open Streamlit dashboard to see results.")

