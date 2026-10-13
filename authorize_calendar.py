from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

ROOT = Path(__file__).resolve().parent

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events"
]


def main():
    credentials_file = ROOT / "credentials.json"

    if not credentials_file.exists():
        raise SystemExit(
            "credentials.json must be beside this script."
        )

    flow = InstalledAppFlow.from_client_secrets_file(
        str(credentials_file),
        SCOPES,
    )

    credentials = flow.run_local_server(
        host="localhost",
        port=0,
        prompt="consent",
        access_type="offline",
    )

    token_file = ROOT / "token.json"
    token_file.write_text(
        credentials.to_json(),
        encoding="utf-8",
    )

    print("Authorization completed. token.json saved.")
    print("No calendar events have been created.")


if __name__ == "__main__":
    main()