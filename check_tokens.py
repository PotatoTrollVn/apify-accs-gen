import json
import requests
import os

def check_apify_key(api_key):
    url = f"https://api.apify.com/v2/users/me?token={api_key}"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            return True
        elif response.status_code in [401, 403]:
            return False
        else:
            print(f"  Unexpected status code: {response.status_code}")
            return False
    except Exception as e:
        print(f"  Error checking key: {e}")
        return False

def clean_tokens():
    token_file_path = "apify_token.json"
    
    if not os.path.exists(token_file_path):
        print(f"File {token_file_path} not found.")
        return

    with open(token_file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    keys = data.get("apify_api_keys", [])
    valid_keys = []
    invalid_keys = []

    print(f"Checking {len(keys)} Apify accounts...")
    for idx, key in enumerate(keys, 1):
        print(f"[{idx}/{len(keys)}] Checking key: {key[:15]}...")
        if check_apify_key(key):
            print("  [+] Key is valid.")
            valid_keys.append(key)
        else:
            print("  [-] Key is invalid or out of credits.")
            invalid_keys.append(key)

    data["apify_api_keys"] = valid_keys
    with open(token_file_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)
        
    print(f"\nDone! Valid keys: {len(valid_keys)}, Invalid keys removed: {len(invalid_keys)}")

if __name__ == "__main__":
    clean_tokens()
