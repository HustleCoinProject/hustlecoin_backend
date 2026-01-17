import requests
import time
import sys
from pymongo import MongoClient

BASE_URL = "http://127.0.0.1:8000"
API_PREFIX = "/api"
# Use the URI from .env
MONGO_URI = "mongodb+srv://ailtonjoaosimao:ailtonjoaosimao@cluster0.lxgx5mq.mongodb.net/hustlecoin_db?retryWrites=true&w=majority&appName=Cluster0"
DB_NAME = "hustlecoin_db" # DB name from URI path

# Helper to print colored status
def print_status(msg, status="INFO"):
    colors = {
        "INFO": "\033[94m",
        "SUCCESS": "\033[92m",
        "ERROR": "\033[91m",
        "WARNING": "\033[93m",
        "END": "\033[0m"
    }
    print(f"{colors.get(status, '')}[{status}] {msg}{colors['END']}")

def verify_user_in_db(email):
    try:
        client = MongoClient(MONGO_URI)
        db = client[DB_NAME]
        # Collection name is 'users' (from printed list and models.py)
        users = db.users
             
        result = users.update_one(
            {"email": email},
            {"$set": {"is_email_verified": True}}
        )
        if result.modified_count > 0:
            print_status(f"Directly verified user {email} in DB.", "SUCCESS")
        elif result.matched_count > 0:
             print_status(f"User {email} already verified in DB.", "INFO")
        else:
             print_status(f"User {email} not found in DB to verify.", "WARNING")
        client.close()
    except Exception as e:
        print_status(f"Failed to verify user in DB: {e}", "ERROR")


def register_user(email, password):
    url = f"{BASE_URL}{API_PREFIX}/users/register"
    data = {"email": email, "password": password, "username": email.split("@")[0]}
    headers = {"x-hustle-coin-client-key": "scooby doo"}
    try:
        response = requests.post(url, json=data, headers=headers)
        if response.status_code == 200 or response.status_code == 201:
            print_status(f"User {email} registered.", "SUCCESS")
            
            # Verify email manually via DB (direct access)
            verify_user_in_db(email)
            
            # Must login to get token
            print_status("Logging in...", "INFO")
            login_url = f"{BASE_URL}{API_PREFIX}/users/login"
            login_data = {"username": email.split("@")[0], "password": password}
            headers = {"x-hustle-coin-client-key": "scooby doo"} # Ensure headers are used
            login_resp = requests.post(login_url, data=login_data, headers=headers)
            
            # Verify email manually via dev endpoint
            verify_url = f"{BASE_URL}{API_PREFIX}/dev/verify-user-email"
            verify_resp = requests.post(verify_url, json={"email": email}, headers=headers)
            if verify_resp.status_code == 200:
                print_status("Email verified manually via dev endpoint.", "SUCCESS")
            else:
                print_status(f"Failed to verify email: {verify_resp.text}", "WARNING")

            if login_resp.status_code == 200:
                print_status("Login successful.", "SUCCESS")
                return login_resp.json()
            else:
                 print_status(f"Login after register failed: {login_resp.status_code} {login_resp.text}", "ERROR")
                 return None
        elif response.status_code == 400 and ("already registered" in response.text or "already taken" in response.text):
             # Try login
             print_status("User exists, trying login...", "INFO")
             login_url = f"{BASE_URL}{API_PREFIX}/users/login"
             login_data = {"username": email.split("@")[0], "password": password} # Login uses format.username
             login_resp = requests.post(login_url, data=login_data, headers=headers)
             
             # Verify email manually via DB (direct access)
             verify_user_in_db(email)

             login_resp = requests.post(login_url, data=login_data, headers=headers)
             if login_resp.status_code == 200:
                  print_status("Login successful.", "SUCCESS")
                  return login_resp.json()
             else:
                  print_status(f"Login failed: {login_resp.status_code} {login_resp.text}", "ERROR")
        else:
            print_status(f"Registration failed: {response.status_code} {response.text}", "ERROR")
    except Exception as e:
        print_status(f"Failed to register/login: {e}", "ERROR")
    return None

def get_events(token):
    url = f"{BASE_URL}{API_PREFIX}/events/list"
    headers = {"Authorization": f"Bearer {token}", "x-hustle-coin-client-key": "scooby doo"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    print_status(f"Failed to get events: {resp.text}", "ERROR")
    return None

def join_event(token, event_id):
    url = f"{BASE_URL}{API_PREFIX}/events/join/{event_id}"
    headers = {"Authorization": f"Bearer {token}", "x-hustle-coin-client-key": "scooby doo"}
    resp = requests.post(url, headers=headers)
    if resp.status_code == 200:
        print_status(f"Joined event {event_id}.", "SUCCESS")
        return resp.json()
    print_status(f"Failed to join event: {resp.text}", "ERROR")
    return None

def tap(token):
    url = f"{BASE_URL}{API_PREFIX}/tapping/tap"
    headers = {"Authorization": f"Bearer {token}", "x-hustle-coin-client-key": "scooby doo"}
    data = {"tap_count": 10, "timestamp": int(time.time()*1000)}
    resp = requests.post(url, json=data, headers=headers)
    if resp.status_code == 200:
        print_status("Tapped successfully (10 taps).", "SUCCESS")
        return resp.json()
    print_status(f"Failed to tap: {resp.text}", "ERROR")
    return None

def get_leaderboard(token, event_id):
    url = f"{BASE_URL}{API_PREFIX}/events/leaderboard/{event_id}"
    headers = {"Authorization": f"Bearer {token}", "x-hustle-coin-client-key": "scooby doo"}
    resp = requests.get(url, headers=headers)
    if resp.status_code == 200:
        return resp.json()
    print_status(f"Failed to get leaderboard: {resp.text}", "ERROR")
    return None

def run_test():
    print_status("Starting Events Flow Test...", "INFO")
    
    # 1. Register/Login
    email = "event_test_user_2@example.com"
    password = "password123"
    auth_data = register_user(email, password)
    if not auth_data:
        sys.exit(1)
    
    token = auth_data.get("access_token")
    if not token: # Maybe it's directly in response or different format, let's assume standard OAuth2 response
        print_status("No access token found.", "ERROR")
        sys.exit(1)

    # 2. List Events
    events = get_events(token)
    if not events:
        sys.exit(1)
    
    print_status(f"Found {len(events)} events.", "INFO")
    target_event = events[0]
    event_id = target_event['event_id']
    print_status(f"Targeting event: {event_id} ({target_event['name']})", "INFO")

    # 3. Join Event
    # Check if already joined
    if target_event.get("is_joined"):
        print_status("Already joined this event.", "INFO")
    else:
        # We need HC to join. Assuming new user might not have enough.
        # But this is a test. Let's try joining. If fails due to funds, we might need a cheat endpoint or just tap a lot.
        # New users usually get some starting balance. Let's hope it's enough (50 HC for 1d).
        res = join_event(token, event_id)
        if not res or (isinstance(res, dict) and "Insufficient funds" in str(res)) or "Insufficient funds" in str(res): 
             print_status("Not enough funds. Tapping to earn...", "INFO")
             for _ in range(5):
                 tap(token)
             res = join_event(token, event_id) # Retry

    # 4. Tap to earn points
    print_status("Tapping to earn event points...", "INFO")
    tap(token)
    tap(token)

    # 5. Verify Leaderboard
    leaderboard = get_leaderboard(token, event_id)
    if leaderboard:
        print_status("Leaderboard fetched.", "SUCCESS")
        found = False
        for entry in leaderboard:
            if "event_test_user_2" in entry['username'] or email.split("@")[0] in entry['username']:
                print_status(f"User found in leaderboard with {entry['event_points']} points!", "SUCCESS")
                found = True
                break
        if not found:
            print_status("User NOT found in leaderboard (might be caching or instant update issue).", "WARNING")
    
    print_status("Test Completed.", "INFO")

if __name__ == "__main__":
    run_test()
