import sqlite3

from flask import Flask, render_template, redirect, url_for, request
from jobs_db import init_db, DB_FILE
from gmail_search_jobs_ import scan_gmail_by_date_range
from datetime import datetime, timedelta


app = Flask(__name__)

def format_display_date(date_value):
    if not date_value:
        return ""
    
    try:
        return datetime.strptime(date_value, "%Y-%m-%d").strftime("%-m/%-d/%y")
    except Exception:
        return date_value
    

def get_job_emails():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
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
            created_at,
            updated_at,
            snippet
        FROM job_emails
        ORDER BY datetime(COALESCE(last_update_date, date_received, created_at)) DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    emails = []

    for row in rows:
        email = dict(row)
        email["date_received_display"] = format_display_date(email["date_received"])
        email["last_update_display"] = format_display_date(email.get("last_update_date"))
        emails.append(email)
        
    return emails

def get_status_counts():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("""
        SELECT status, COUNT(*) as count
        FROM job_emails
        GROUP BY status
        ORDER BY count DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    return rows


@app.route("/")
def dashboard():
    init_db()

    emails = get_job_emails()
    status_counts = get_status_counts()

    total_emails = sum(row[1] for row in status_counts)

    return render_template(
        "dashboard.html",
        emails = emails,
        status_counts=status_counts,
        total_emails=total_emails
    )

@app.route("/scan-last-day", methods=["POST"])
def scan_last_day():
    scan_gmail_by_date_range(last_24_hours=True)

    return redirect(url_for("dashboard"))

@app.route("/scan-custom-range", methods=["POST"])
def scan_custom_range():
    start_date_raw = request.form.get("start_date")
    end_date_raw = request.form.get("end_date")

    start_date = start_date_raw

    end_date_obj = datetime.strptime(end_date_raw, "%Y-%m-%d")
    end_date = (end_date_obj + timedelta(days=1)).strftime("%Y-%m-%d")

    scan_gmail_by_date_range(start_date, end_date)

    return redirect(url_for("dashboard"))

if __name__ == "__main__":
    app.run(debug=True, port=5003)

