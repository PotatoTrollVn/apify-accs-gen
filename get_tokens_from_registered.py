import json
import time
import os
import re
from DrissionPage import ChromiumOptions, ChromiumPage

ACCOUNTS_FILE = "registered_accounts.json"
VERIFIED_OUTPUT = "apify_token.json"

def get_tokens_from_registered():
    if not os.path.exists(ACCOUNTS_FILE):
        print(f"Không tìm thấy file {ACCOUNTS_FILE}")
        return

    try:
        with open(ACCOUNTS_FILE, "r", encoding="utf-8") as f:
            accounts = json.load(f)
    except Exception as e:
        print(f"Lỗi đọc file: {e}")
        return

    if not accounts:
        print("Không có tài khoản nào trong danh sách.")
        return

    try:
        with open(VERIFIED_OUTPUT, "r", encoding="utf-8") as f:
            verified_keys = json.load(f).get("apify_api_keys", [])
    except:
        verified_keys = []

    print(f"Tìm thấy {len(accounts)} tài khoản trong {ACCOUNTS_FILE}.")
    print("Bắt đầu đăng nhập và lấy API Token...\n")

    co = ChromiumOptions()
    co.auto_port()
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.incognito(True)
    page = ChromiumPage(co)

    try:
        for idx, account in enumerate(accounts, 1):
            email = account.get("email")
            password = account.get("password")
            if not email or not password:
                continue

            print(f"[{idx}/{len(accounts)}] Lấy Token cho: {email}")

            try:
                page.get("https://console.apify.com/sign-in")
                page.wait.load_start()
                time.sleep(2)
                page.run_js("localStorage.clear(); sessionStorage.clear();")
                page.clear_cache(cookies=True)
                page.get("https://console.apify.com/sign-in")
                time.sleep(2)

                # Find and click 'Continue with email' if needed
                print("  [LOGIN] Đang tìm nút Continue with email...")
                try:
                    email_btn = page.ele('text:Continue with email', timeout=3) or page.ele('text:Sign in with email', timeout=3) or page.ele('button:has-text("email")', timeout=3)
                    if email_btn:
                        email_btn.click()
                        time.sleep(1)
                except: pass

                email_ele = page.ele('@name=email', timeout=5) or page.ele('@type=email', timeout=5)
                if email_ele:
                    print("  [LOGIN] Đã thấy ô điền email.")
                    email_ele.clear()
                    email_ele.input(email)
                    time.sleep(0.5)

                    next_btn = page.ele('xpath://button[@type="submit"]') or page.ele('button:has-text("Continue")') or page.ele('button:has-text("Next")')
                    if next_btn:
                        page.run_js('arguments[0].click();', next_btn)
                        time.sleep(2)

                    pw_ele = page.ele('@name=password', timeout=5) or page.ele('@type=password', timeout=5)
                    if pw_ele:
                        pw_ele.clear()
                        pw_ele.input(password)

                    login_btn = page.ele('xpath://button[@type="submit"]') or page.ele('button:has-text("Sign in")')
                    if login_btn:
                        page.run_js('arguments[0].click();', login_btn)
                        print("  [LOGIN] Đã bấm nút Sign In, chờ tải trang...")
                        time.sleep(5)
                else:
                    print("  [ERROR] Không tìm thấy form điền email đăng nhập. Vui lòng kiểm tra lại mạng hoặc giao diện Apify.")
                    continue

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
                        page.get("https://console.apify.com/settings/integrations")
                        time.sleep(2)
                except:
                    page.get("https://console.apify.com/settings/integrations")
                    time.sleep(2)

                # Try to click the reveal button so the token appears in HTML
                reveal_btn = page.ele('@data-test=toggle-visibility-button', timeout=3)
                if reveal_btn:
                    reveal_btn.click()
                    time.sleep(1)

                body_text = page.ele('tag:body').text
                keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body_text)
                if not keys:
                    copy_btn = page.ele('@data-test=copy_to_clipboard', timeout=1)
                    if copy_btn:
                        copy_btn.click()
                        time.sleep(0.5)
                        
                    body_text = page.ele('tag:body').text
                    keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body_text)

                if keys:
                    api_key = keys[0]
                    print(f"  ✅ [SUCCESS] Tìm thấy API Key: {api_key[:15]}...")
                    if api_key not in verified_keys:
                        verified_keys.append(api_key)
                        with open(VERIFIED_OUTPUT, "w", encoding="utf-8") as f:
                            json.dump({"apify_api_keys": verified_keys}, f, indent=4)
                        print(f"  [SAVE] Đã lưu vào {VERIFIED_OUTPUT}")
                else:
                    print("  ❌ Không tìm thấy API Token. Có thể trang load chậm hoặc chưa reveal được.")

            except Exception as e:
                print(f"  [ERROR] {e}")

            time.sleep(2)

    finally:
        page.quit()

    print("\n🎉 Hoàn tất kiểm tra và lấy token từ danh sách có sẵn.")

if __name__ == "__main__":
    get_tokens_from_registered()
