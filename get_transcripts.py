import os
import requests
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

# ===== CONFIG =====
TENANT_ID     = os.environ.get("TEAMS_TENANT_ID",     "5a12c187-c285-4bea-8b0d-bbad28317395")
CLIENT_ID     = os.environ.get("TEAMS_CLIENT_ID",     "927647b7-fc5a-47b9-817a-c037087b4e7f")
CLIENT_SECRET = os.environ.get("TEAMS_CLIENT_SECRET", "pf58Q~ZvxOO2Qovdli0fT2qOMqpy3UvykcXtBa2d")
TARGET_USER   = os.environ.get("TEAMS_TARGET_USER",   "thunyaporn.tra@cosmic-3c.com")
DAYS_BACK     = 30
# ==================


class AppAccessPolicyError(RuntimeError):
    pass

def get_access_token(tenant_id=None, client_id=None, client_secret=None):
    tid     = tenant_id     or TENANT_ID
    cid     = client_id     or CLIENT_ID
    csecret = client_secret or CLIENT_SECRET
    url = f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token"
    data = {
        "grant_type":    "client_credentials",
        "client_id":     cid,
        "client_secret": csecret,
        "scope":         "https://graph.microsoft.com/.default",
    }
    r = requests.post(url, data=data)
    r.raise_for_status()
    return r.json()["access_token"]


def get_graph_error_message(response):
    try:
        error = response.json().get("error", {})
        code = error.get("code", "unknown")
        message = error.get("message", response.text[:200])
        return f"{code}: {message}"
    except ValueError:
        return response.text[:200]


def get_user_id(token, user):
    headers = {"Authorization": f"Bearer {token}"}
    params = {"$select": "id,displayName,userPrincipalName"}
    r = requests.get(f"https://graph.microsoft.com/v1.0/users/{user}", headers=headers, params=params)
    r.raise_for_status()
    return r.json()["id"]


def get_calendar_events(token, user, days_back=30):
    now   = datetime.now(timezone.utc)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%dT%H:%M:%SZ")
    end   = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    url     = f"https://graph.microsoft.com/v1.0/users/{user}/calendarView"
    headers = {"Authorization": f"Bearer {token}"}
    params  = {
        "startDateTime": start,
        "endDateTime":   end,
        "$select":       "subject,start,onlineMeeting,isOnlineMeeting",
        "$top":          100,
    }
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    events = r.json().get("value", [])
    return [e for e in events if e.get("isOnlineMeeting")]


def get_meeting_by_join_url(token, user_id, join_url):
    """หา meeting โดยใช้ joinUrl ผ่าน endpoint ที่รองรับ app permission"""
    headers = {"Authorization": f"Bearer {token}"}
    encoded_join_url = quote(join_url, safe="")
    url = (
        f"https://graph.microsoft.com/v1.0/users/{user_id}/onlineMeetings"
        f"?$filter=JoinWebUrl%20eq%20'{encoded_join_url}'"
    )
    r = requests.get(url, headers=headers)
    if r.status_code == 400:
        print(f"  Graph lookup failed: {get_graph_error_message(r)}")
        return None
    if r.status_code == 404:
        return None
    if r.status_code == 403:
        raise AppAccessPolicyError(get_graph_error_message(r))
    r.raise_for_status()
    meetings = r.json().get("value", [])
    if meetings:
        return meetings[0]
    return None


def get_transcripts(token, user_id, meeting_id):
    url     = f"https://graph.microsoft.com/v1.0/users/{user_id}/onlineMeetings/{meeting_id}/transcripts"
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 404:
        return []
    if r.status_code == 403:
        raise AppAccessPolicyError(get_graph_error_message(r))
    r.raise_for_status()
    return r.json().get("value", [])


def get_transcript_content(token, user_id, meeting_id, transcript_id):
    url = (
        f"https://graph.microsoft.com/v1.0/users/{user_id}"
        f"/onlineMeetings/{meeting_id}/transcripts/{transcript_id}/content"
        f"?$format=text/vtt"
    )
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers)
    if r.status_code == 403:
        raise AppAccessPolicyError(get_graph_error_message(r))
    r.raise_for_status()
    try:
        return r.content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return r.text


def main():
    print("Getting token...")
    token = get_access_token()
    target_user_id = get_user_id(token, TARGET_USER)

    print(f"Getting calendar events (last {DAYS_BACK} days) for {TARGET_USER}...")
    events = get_calendar_events(token, TARGET_USER, DAYS_BACK)
    print(f"Found {len(events)} online meeting events\n")

    try:
        for event in events:
            subject  = event.get("subject", "(no subject)")
            start    = event.get("start", {}).get("dateTime", "")
            join_url = event.get("onlineMeeting", {}).get("joinUrl", "")

            if not join_url:
                continue

            print(f"Meeting: {subject} | {start[:16]}")

            meeting = get_meeting_by_join_url(token, target_user_id, join_url)
            if not meeting:
                print("  No meeting record found\n")
                continue

            meeting_id  = meeting["id"]
            transcripts = get_transcripts(token, target_user_id, meeting_id)

            if not transcripts:
                print("  No transcripts\n")
                continue

            for t in transcripts:
                transcript_id = t["id"]
                created_at    = t.get("createdDateTime", "")
                print(f"  Transcript: {created_at}")

                content = get_transcript_content(token, target_user_id, meeting_id, transcript_id)

                safe_subject = "".join(c for c in subject if c.isalnum() or c in " -_")[:50]
                filename     = f"transcript_{safe_subject}_{transcript_id[:8]}.vtt"
                with open(filename, "w", encoding="utf-8") as f:
                    f.write(content)
                print(f"  Saved: {filename}")

            print()
    except AppAccessPolicyError as exc:
        print(f"  Graph access denied: {exc}")
        print("  Configure and grant a Teams application access policy for this app, then run the script again.")


if __name__ == "__main__":
    main()
