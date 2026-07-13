import os
import sqlite3
import re

DATA_DIR = "data"
DB_FILE = os.path.join(DATA_DIR, "job_tracker.db")

def init_db():
    os.makedirs(DATA_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS job_emails(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            gmail_message_id TEXT UNIQUE,
            date_received TEXT,
            last_update_date TEXT,
            sender TEXT,
            subject TEXT,
            latest_subject TEXT,
            status TEXT,
            company TEXT,
            role_title TEXT,
            location TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            snippet TEXT
        )
    """)

    conn.commit()
    conn.close()


def normalize_text(value):
    if not value:
        return ""
    
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9\s]", " ", value)
    value = re.sub(r"\s", " ", value)

    return value

def find_existing_application(cursor, company=None, role_title=None, sender=None, subject=None):
    normalized_company = normalize_text(company)
    normalized_role = normalize_text(role_title)
    normalize_subject = normalize_text(subject)

    cursor.execute("""
        SELECT *
        FROM job_emails
        ORDER BY datetime(COALESCE(date_received, created_at)) DESC
    """)

    rows = cursor.fetchall()

    for row in rows:
        existing_company = normalize_text(row["company"] if "company" in row.keys() else None)
        existing_role = normalize_text(row["role_title"] if "role_title" in row.keys() else None)
        existing_subject = normalize_text(row["subject"] if "subject" in row.keys() else None)

        if normalized_company and normalized_role:
            if existing_company == normalized_company and existing_role == normalized_role:
                return row

        combined_text = normalize_text(f"{sender or ''} {subject or ''}")

        if normalized_role and existing_role == normalized_role:
            if existing_company and existing_company in combined_text:
                return row
        
        if normalize_subject and existing_role:
            if normalize_subject == existing_role:
                return row
    
    return None

def save_email(gmail_message_id, date_received, sender, subject, status, snippet, company=None, role_title=None, location=None):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM job_emails
        WHERE gmail_message_id = ?    
    """, (gmail_message_id,))

    exact_existing = cursor.fetchone()

    if exact_existing:
        cursor.execute("""
        UPDATE job_emails
        SET date_received = COALESCE(NULLIF(date_received, ''), ?)
        WHERE gmail_message_id = ?
    """, (date_received, gmail_message_id))
        
        conn.commit()
        conn.close()
        return False
    
    existing_application = find_existing_application(cursor, company=company, role_title=role_title, sender=sender, subject=subject)

    if existing_application:
        cursor.execute("""
            UPDATE job_emails
            SET
                status = ?,
                last_update_date = ?,
                latest_subject = ?,
                sender = ?,
                snippet = ?,
                subject = ?,
                gmail_message_id = ?,
                company = COALESCE(NULLIF(?, ''), company),
                role_title = COALESCE(NULLIF(?, ''), role_title),
                location = COALESCEd(NULLIF(?, ''), location),
                updated_at = datetime('now')
            WHERE id = ?
        """, (status, date_received, subject, sender, snippet, gmail_message_id, company, role_title, location, existing_application["id"]))

        conn.commit()
        conn.close()
        return True

    cursor.execute("""
        INSERT INTO job_emails (
            gmail_message_id,
            date_received,
            last_update_date,
            sender,
            subject,
            latest_subject,
            status,
            company,
            role_title,
            location,
            snippet,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))
    """, (
        gmail_message_id,
        date_received,
        date_received,
        sender,
        subject,
        subject,
        status,
        company,
        role_title,
        location,
        snippet
    ))

    conn.commit()
    conn.close()
    return True