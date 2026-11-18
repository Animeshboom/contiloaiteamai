"""One-time Google OAuth 2.0 consent for the Gmail MCP server.

    GMAIL_CREDENTIALS_FILE=secrets/client_secret.json GMAIL_TOKEN_FILE=secrets/gmail_token.json \\
        python -m gmail_mcp.authorize

Opens a browser for consent (scope: gmail.compose only) and stores the refreshable
user token at GMAIL_TOKEN_FILE. Keep both files out of version control.
"""
import os
import sys
from pathlib import Path

from gmail_mcp.config import GMAIL_SCOPES


def main() -> None:
    creds_file = os.environ.get("GMAIL_CREDENTIALS_FILE")
    token_file = os.environ.get("GMAIL_TOKEN_FILE")
    if not creds_file or not Path(creds_file).is_file():
        sys.exit("Set GMAIL_CREDENTIALS_FILE to the OAuth client JSON downloaded from Google Cloud Console.")
    if not token_file:
        sys.exit("Set GMAIL_TOKEN_FILE to where the user token should be stored.")
    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(creds_file, GMAIL_SCOPES)
    creds = flow.run_local_server(port=0, prompt="consent", access_type="offline")
    Path(token_file).parent.mkdir(parents=True, exist_ok=True)
    Path(token_file).write_text(creds.to_json(), encoding="utf-8")
    try:
        os.chmod(token_file, 0o600)
    except OSError:
        pass
    print(f"Saved Gmail token to {token_file} (scope: {', '.join(GMAIL_SCOPES)})")


if __name__ == "__main__":
    main()
