import json
import time
import requests
import re
import sys
import os
from DrissionPage import ChromiumPage, ChromiumOptions

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

ACCOUNTS_FILE = "registered_accounts.json"
VERIFIED_OUTPUT = "apify_token.json"

def get_inbox_mailtm(email: str, password: str):
    try:
        r = requests.post("https://api.mail.tm/token", json={"address": email, "password": password}, timeout=10)
        if r.status_code != 200:
            return None, None
        token = r.json()["token"]
        
        r = requests.get("https://api.mail.tm/messages", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            return r.json(), token
        return None, token
    except Exception:
        return None, None

def get_message_content_mailtm(message_id: str, token: str):
    try:
        r = requests.get(f"https://api.mail.tm/messages/{message_id}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
        if r.status_code == 200:
            msg_data = r.json()
            return msg_data.get("html", "") or msg_data.get("text", "")
        return None
    except Exception:
        return None

def verify_and_get_apify_key(page: ChromiumPage, verify_link: str, account: dict):
    print(f"  [VERIFY] Navigating to Apify verification link...")
    try:
        page.get("https://console.apify.com")
        page.run_js("localStorage.clear(); sessionStorage.clear();")
    except: pass
    
    page.get(verify_link)
    page.wait.load_start()
    time.sleep(3)

    print("  [API] Đang điều hướng đến Settings...")
    try:
        page.get("https://console.apify.com/")
        time.sleep(2)
        settings_btn = page.ele('@id=Navigation_id_ACCOUNT', timeout=5) or page.ele('@href=/settings', timeout=5)
        if settings_btn:
            settings_btn.click()
            time.sleep(1)
            
        print("  [API] Đang mở tab API & Integrations...")
        int_tab = page.ele('@id=INTEGRATIONS', timeout=5) or page.ele('@data-test=tab-integrations', timeout=5)
        if int_tab:
            int_tab.click()
            time.sleep(2)
        else:
            # Fallback direct get
            page.get("https://console.apify.com/settings/integrations")
            time.sleep(2)
    except:
        page.get("https://console.apify.com/settings/integrations")
        time.sleep(2)
    
    try:
        # Try to click the reveal button so the token appears in HTML
        reveal_btn = page.ele('@data-test=toggle-visibility-button', timeout=3)
        if reveal_btn:
            reveal_btn.click()
            time.sleep(1)
            
        body_text = page.ele('tag:body').text
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body_text)
        if keys:
            print(f"  ✅ [SUCCESS] Found Apify API Key: {keys[0][:15]}...")
            return keys[0]
            
        print("  ⚠️ Could not find Apify token on the page. Trying to click any copy buttons...")
        copy_btn = page.ele('@data-test=copy_to_clipboard', timeout=1)
        if copy_btn:
            copy_btn.click()
            time.sleep(0.5)
            
        # Try finding the token again
        body_text = page.ele('tag:body').text
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body_text)
        if keys:
            print(f"  ✅ [SUCCESS] Found Apify API Key: {keys[0][:15]}...")
            return keys[0]
    except Exception as e:
        print(f"  [ERROR] Could not extract Apify API key: {e}")

    return None

def remove_from_registered(email: str):
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            current_accounts = json.load(f)
        filtered = [a for a in current_accounts if a["email"] != email]
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as f:
            json.dump(filtered, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def process_verifications():
    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except Exception as e:
        print(f"Could not read {ACCOUNTS_FILE}: {e}")
        return
        
    if not accounts:
        print(f"Không có tài khoản nào cần verify.")
        return

    try:
        with open(VERIFIED_OUTPUT, "r", encoding="utf-8") as f:
            verified_data = json.load(f)
            verified_keys = verified_data.get("apify_api_keys", [])
    except Exception:
        verified_keys = []

    co = ChromiumOptions()
    co.auto_port()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.incognito(True)
    page = ChromiumPage(co)

    try:
        for idx, account in enumerate(accounts, 1):
            email = account["email"]
            print(f"\n{'='*50}\n[{idx}/{len(accounts)}] Verifying {email}\n{'='*50}")
            
            if "mailtm_password" not in account:
                print("Không tìm thấy mật khẩu Mail.tm.")
                continue

            message_id = None
            mailtm_token = None
            
            print("  [WAIT] Đang chờ email xác nhận từ Apify (tối đa 60s)...")
            for _ in range(12):
                inbox, token = get_inbox_mailtm(email, account["mailtm_password"])
                if inbox:
                    inbox_str = json.dumps(inbox).lower()
                    if "apify" in inbox_str:
                        messages = inbox.get("hydra:member", [])
                        for msg in messages:
                            if isinstance(msg, dict):
                                subject = msg.get("subject", "").lower()
                                sender = msg.get("from", {}).get("address", "").lower() if isinstance(msg.get("from"), dict) else ""
                                print(f"  [DEBUG] Found email: '{subject}' from {sender}")
                                if "verify" in subject or "confirm" in subject or "action required" in subject or "email" in subject:
                                    message_id = msg.get("id") or msg.get("messageID")
                                    mailtm_token = token
                                    break
                if message_id:
                    break
                time.sleep(2)
            
            if not message_id:
                print(f"  ⚠️ Không nhận được email từ Apify sau 60s.")
                continue
                
            print(f"  [INBOX] Found message ID: {str(message_id)[:15]}...")
            content = get_message_content_mailtm(message_id, mailtm_token)
            if not content:
                continue
                
            if isinstance(content, list):
                content = " ".join([str(c) for c in content])
            elif not isinstance(content, str):
                content = str(content)
                
            # Improved regex to catch any verify link from apify
            links = re.findall(r'(https://[a-zA-Z0-9\-\.]*apify\.com[^\s\"\'>]+)', content)
            verify_link = None
            for l in links:
                l = l.replace('\\/', '/')
                if 'verify' in l.lower() or 'confirm' in l.lower():
                    verify_link = l
                    break
                    
            if not verify_link:
                print("  [WARNING] Could not find verification link in email body.")
                print(f"  [DEBUG] Content preview: {content[:500]}")
                continue
                
            print(f"  [INBOX] Extracted verify link.")
            
            api_key = verify_and_get_apify_key(page, verify_link, account)
            if api_key:
                if api_key not in verified_keys:
                    verified_keys.append(api_key)
                
                with open(VERIFIED_OUTPUT, "w", encoding="utf-8") as f:
                    json.dump({"apify_api_keys": verified_keys}, f, indent=4)
                print(f"  [SAVE] Saved API key to {VERIFIED_OUTPUT}")
                remove_from_registered(email)
            
            time.sleep(1)
    finally:
        page.quit()

if __name__ == "__main__":
    process_verifications()
