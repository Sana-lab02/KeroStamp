import os.path

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
            creds.refresh(Request())
        else:
            if not os.path.exists("creds.json"):
                raise FileNotFoundError(
                    "Missing creds.json. Download it from Google Cloud Console and place it in this project folder"
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                "creds.json",
                SCOPES
            )
            creds = flow.run_local_server(
                port=0,
                prompt="select_account"
            )

        with open("token.json", "w") as token:
            token.write(creds.to_json())
    
    return build("gmail", "v1", credentials=creds)
    

def main():
    service = get_gmail_service()

    profile = service.users().getProfile(userId="me").execute()

    print("Gmail auth worked.")
    print("Email:", profile.get("emailAddress"))
    print("Total messages:", profile.get("messagesTotal"))
    print("Total Threads:", profile.get("threadsTotal"))

if __name__ == "__main__":
    main()