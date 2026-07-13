import sqlite3

DB_FILE = "job_tracker.db"

def main():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date_received, sender, subject, status
        FROM job_emails
        ORDER BY date_received DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    print(f"Found {len(rows)} saved job emails. \n")

    for date_received, sender, subject, status in rows:
        print("-------")
        print("Date:", date_received)
        print("Status:", status)
        print("From:", sender)
        print("Subject", subject)

if __name__ == "__main__":
    main()