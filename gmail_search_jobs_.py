import os.path
import base64
from email.utils import parsedate_to_datetime
from jobs_db import init_db, save_email
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


def get_gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print("Token refresh failed: {e}")
                if os.path.exists("toke.json"):
                    os.remove("token.json")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json",
                    SCOPES
                )

                creds = flow.run_local_server(port=0)
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("gmail", "v1", credentials=creds)

def get_header(headers, name):
    for header in headers:
        if header["name"].lower() == name.lower():
            return header["value"]
    return ""

def is_junk_job_email(sender, subject):
    text = f"{sender}  {subject}".lower()

    junk_patterns = [
        "newsletters-noreply@linkedin.com",
        "jobalerts-noreply@linkedin.com",
        "linkedin job alert",
        "indeed job alert",
        "recommended jobs",
        "new jobs for you",
        "hiring now",
        "newsletter",
        "glassdoor job alert",
        "stop running recruiting",
    ]

    return any(pattern in text for pattern in junk_patterns)

def classify_email(subject, sender="", snippet="", body_text=""):
    text = f"{subject}  {sender} {snippet} {body_text or ''}".lower()

    if any(phrase in text for phrase in [
        "unfortunately",
        "not moving forward",
        "pursue other candidates",
        "after careful consideration",
        "not selected",
        "we will not be moving forward",
        "decided to move forward with other candidates"
    ]):
        return "REJECTED"
    
    if any(phrase in text for phrase in [
        "interview",
        "schedule a call",
        "schedule an interview",
        "phone screen",
        "recruiter screen",
        "technical interview",
        "availability"
    ]):
        return "INTERVIEW"
    
    if any(phrase in text for phrase in [
        "schedule a call",
        "schedule time",
        "book a time",
        "calendar link",
        "calendly",
        "are you available",
        "would love to chat",
        "would like to chat",
        "connect with you",
        "speak with you",
        "discuss the role",
        "discuss your application",
        "talk about the role",
        "learn more about your experience",
        "reached out",
        "following up on your application",
    ]):
        return "RECRUITER CONTACT"

    
    if any(phrase in text for phrase in [
        "assessment",
        "coding challenge",
        "take-home",
        "technical exercise",
        "online assessment"
    ]):
        return "ASSESSMENT"
    
    if any(phrase in text for phrase in [
        "thank you for applying",
        "thanks for applying",
        "application received",
        "application submitted",
        "we received your application",
        "your application has been submitted",
        "your application was sent",
        "your application is complete"
    ]):
        return "APPLIED"
    
    if any(phrase in text for phrase in [
        "complete your application",
        "finish your application",
        "not done with your application",
        "please complete your online application"
    ]):
        return "FINISH APPLICATION"
    
    return "UNKNOWN"

def build_job_keywords_query():
    return(
        '('
        '"thank you for applying" OR '
        '"thanks for applying" OR '
        '"application received" OR '
        '"application submitted" OR '
        '"application is complete" OR'
        '"items sent" OR '
        '"next steps" OR '
        '"employer viewed your application" OR '
        '"we received your application" OR '
        '"your application has been submitted" OR '
        '"your application was sent" OR '
        '"your application is complete" OR'
        '"we have received your resume" OR '
        '"unfortunately, we" OR '
        '"after careful consideration" OR '
        '"not moving forward" OR '
        '"pursue other candidates" OR '
        '"selected for an interview" OR '
        '"schedule an interview" OR '
        '"schedule a phone screen" OR '
        '"recruiter screen" OR '
        '"technical interview" OR '
        '"coding challenge" OR '
        '"take-home assessment"'
        ') '
        '-from:newsletters-noreply@linkedin.com '
        '-from:jobalerts-noreply@linkedin.com '
        '-from:alert@indeed.com '
        '-from:phil@ziprecruiter.com'
        '-subject:newsletter '
        '-subject:"job alert" '
        '-subject:"recommended jobs"'
    )

def build_job_search_query(start_date=None, end_date=None, last_24_hours=False):
    keyword_query = build_job_keywords_query()

    if last_24_hours:
        return f'newer_than:1d {keyword_query}'

    if isinstance(start_date, str):
        start_date_obj = datetime.strptime(start_date, "%Y-%m-%d")
    else:
        start_date_obj = start_date

    if isinstance(end_date, str):
        end_date_obj = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        end_date_obj = end_date

    end_date_obj = end_date_obj + timedelta(days=1)

    gmail_after = start_date_obj.strftime("%Y/%m/%d")
    gmail_before = end_date_obj.strftime("%Y/%m/%d")

    return f'after:{gmail_after} before:{gmail_before} {keyword_query}'

def decod_base64url(data):
    if not data:
        return ""
    
    missing_padding = len(data) % 4
    if missing_padding:
        data += "=" * (4 - missing_padding)

    decoded_bytes = base64.urlsafe_b64decode(data)
    return decoded_bytes.decode("utf-8", errors="replace")

def extract_email_body(payload):
    html_parts = []
    plain_parts = []

    def walk(part):
        mime_type = part.get("mimeType", "")
        body = part.get("body", {})
        data = body.get("data")

        if data:
            decoded = decod_base64url(data)

            if mime_type == "text/html":
                html_parts.append(decoded)
            elif mime_type == "text/plain":
                plain_parts.append(decoded)
        
        for child in part.get("parts", []):
            walk(child)
    walk(payload)

    if html_parts:
        return "\n".join(html_parts), "html"
    if plain_parts:
        return "\n".join(plain_parts), "plain"

    return "", "empty"

def scan_gmail_by_date_range(start_date=None, end_date=None, last_24_hours=False):
    init_db()

    service = get_gmail_service()

    query = build_job_search_query(
    start_date=start_date,
    end_date=end_date,
    last_24_hours=last_24_hours
    )

    print("Gmail query:", query)
    

    results = service.users().messages().list(
        userId="me",
        q=query,
        maxResults=600
    ).execute()

    messages = results.get("messages", [])

    print(f"Found {len(messages)} possible job emails. \n")

    saved_count = 0
    existing_count = 0

    for msg in messages:
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="full",
            metadataHeaders=["Subject", "From", "Date"]
        ).execute()
        
        snippet = full_msg.get("snippet", "")
        headers = full_msg["payload"]["headers"]

        body_raw, body_type = extract_email_body(full_msg["payload"])
        body_text = html_to_clean_text(body_raw)

        subject = get_header(headers, "Subject")
        sender = get_header(headers, "From")
        date_raw = get_header(headers, "Date")

        if is_junk_job_email(sender, subject):
            continue

        date_clean = clean_email_date(date_raw)

        status = classify_email(subject, sender, snippet, body_text)
        company = None
        role_title = None
        location = None

        indeed_parsed = parse_indeed_application_email(subject, body_raw)

        if indeed_parsed:
            status = indeed_parsed["status"]
            company = indeed_parsed["company"]
            role_title = indeed_parsed["role_title"]
            location = indeed_parsed["location"]

            snippet = (
                f"Indeed Application | "
                f"Company: {company} | "
                f"Role: {role_title} | "
                f"Location: {location}"
            )

            print("Indeed application parsed:", company, role_title, location)
        elif is_indeed_email(sender, subject, snippet):
            print("Skipped Indeed non-application:", subject)
            continue
        
        else:
            status = classify_email(sender, subject, snippet, body_text)

            if status == "UNKNOWN":
                print("Skipped unknown non-application", subject)
                continue
        
        print("DEBUG DATE")
        print("date_raw:", repr(date_raw))
        print("date_clean:", repr(date_clean))
        print("subject:", subject)

        inserted = save_email(
            gmail_message_id=msg["id"],
            date_received=date_clean,
            sender=sender,
            subject=subject,
            status=status,
            snippet=snippet,
            company=company,
            role_title=role_title,
            location=location
        )

        if inserted:
            saved_count += 1
            print("Saved:", subject)
        else:
            existing_count += 1
            print("Already exists:", subject)
    return {
        "found": len(messages),
        "saved": saved_count,
        "existing": existing_count
    }


def html_to_clean_text(html):
    if not html:
        return ""
    
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style"]):
        tag.decompose()

    text = soup.get_text(separator="\n")

    lines = []

    for line in text.splitlines():
        line = line.strip()
        if line:
            lines.append(line)
    
    return "\n".join(lines)

def parse_indeed_application_email(subject, body_html):
    body_text = html_to_clean_text(body_html)
    lines = body_text.splitlines()


    full_text = f"{subject or ''}\n{body_text}".lower()
    
    skip_phrases = [
        "why don't you apply",
        "recommended jobs",
        "jobs you may like",
        "new jobs for you",
        "job alert",
        "apply now",
        "similar jobs",
    ]

    if any(phrase in full_text for phrase in skip_phrases):
        return None
    
    submit_phrases = [
        "application submitted",
        "your application was sent",
        "you applied",
        "your application has been submitted",
        "your application is complete",
    ]

    if not any(phrases in full_text for phrases in submit_phrases):
        return None
    
    if "application submitted" not in full_text and "your application was sent" not in full_text:
        return None
    
    role_title = get_value_after_label(lines, "Role")
    company = get_value_after_label(lines, "Company")
    location = get_value_after_label(lines, "Location")
    next_steps = get_value_after_label(lines, "Next steps")

    if not role_title:
        fallback_role, fallback_company, fallback_location = parse_indeed_fall_back(lines)
        role_title = fallback_role
        company = fallback_company
        location = fallback_location

    return {
        "source": "Indeed",
        "status": "Applied",
        "company": company,
        "role_title": role_title,
        "location": location,
        "next_steps": next_steps,
        "raw_text": body_text,
    }

def get_value_after_label(lines, label):
    label = label.lower()

    for i, line in enumerate(lines):
        if line.strip().lower() == label:
            if i + 1 < len(lines):
                return lines[i + 1].strip()
    return None

def parse_indeed_fall_back(lines):
    for i, line in enumerate(lines):
        if line.lower() == "application submitted":
            possible_lines = lines[i + 1:i + 6]

            cleaned = [
                x for x in possible_lines
                if x.lower() not in ["role", "location", "items sent", "next steps"]
            ]

            role_title = cleaned[0] if len(cleaned) > 0 else None
            company = cleaned[1] if len(cleaned) > 1 else None
            location = cleaned[2] if len(cleaned) > 2 else None

            return role_title, company, location
    return None, None, None

def clean_email_date(date_raw):
    try:
        dt = parsedate_to_datetime(date_raw)

        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))

        local_dt = dt.astimezone(ZoneInfo("America/Detroit"))

        return local_dt.strftime("%Y-%m-%d")
    except Exception:
        return date_raw

def is_indeed_email(sender, subject, snippet=""):
    text = f"{sender or ''} {subject or ''} {snippet or ''}".lower()
    return "indeed" in text


def main():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=1)

    scan_gmail_by_date_range(start_date, end_date)

if __name__ == "__main__":
    main()