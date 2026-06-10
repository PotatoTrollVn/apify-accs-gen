"""
api_register.py — Hybrid Approach: Browser đăng ký + HTTP lấy key.

Chiến lược:
  ✅ Browser (KHÔNG proxy) → mở signup → fill form → submit → xử lý captcha tự nhiên
  ✅ HTTP (có proxy) → verify email link + login + lấy API key
  
Tại sao:
  - Browser KHÔNG proxy → page load nhanh, không timeout
  - Captcha được xử lý tự nhiên trong browser (không cần extract token)
  - HTTP requests nhẹ (~50KB) → proxy free đủ xử lý
  - Không cần browser navigate đến settings page (tiết kiệm 30-60s)
"""
import os
import sys
import time
import json
import random
import re
import requests
from DrissionPage import ChromiumOptions, ChromiumPage
from GoogleRecaptchaBypass.RecaptchaSolver import RecaptchaSolver
from auto_register import register_apify_account, generate_fake_name, generate_random_password, human_type

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

# ─── Constants ─────────────────────────────────────────────────────
APIFY_BASE = "https://console.apify.com"
APIFY_API_BASE = "https://api.apify.com/v2"


# ═══════════════════════════════════════════════════════════════════
# PHASE 1: Browser Registration (KHÔNG proxy — load nhanh)
# ═══════════════════════════════════════════════════════════════════

class HybridRegistrar:
    """
    Quản lý browser session cho đăng ký.
    Browser chạy KHÔNG proxy → page load nhanh, captcha hoạt động bình thường.
    """
    
    def __init__(self):
        self.page = None
        self._account_count = 0
        self._max_per_session = 3  # Tạo browser mới sau N account (tránh fingerprint)
        self._setup_browser()
    
    def _setup_browser(self):
        """Khởi tạo browser KHÔNG proxy."""
        co = ChromiumOptions()
        co.auto_port()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.incognito(True)
        # KHÔNG set proxy → trang load trực tiếp, nhanh
        # Chặn một số resource không cần thiết
        co.set_argument('--disable-notifications')
        self.page = ChromiumPage(co)
        self._account_count = 0
        print("  [BROWSER] Đã khởi tạo browser mới (không proxy)")
    
    def _maybe_refresh_browser(self):
        """Tạo browser mới sau vài account để tránh fingerprint."""
        self._account_count += 1
        if self._account_count >= self._max_per_session:
            print("  [BROWSER] Đổi session browser mới...")
            self.close()
            time.sleep(1)
            self._setup_browser()
    
    def register_account(self, email, first_name, last_name, password):
        """
        Đăng ký tài khoản Apify trong browser (không proxy).
        Dùng logic đã có từ auto_register.py.
        
        Returns:
            bool: True nếu đăng ký thành công
        """
        try:
            # Clear state trước khi đăng ký account mới
            try:
                self.page.run_js("localStorage.clear(); sessionStorage.clear();")
                self.page.clear_cache(cookies=True)
            except:
                pass
            
            # Dùng hàm register đã có (đã xử lý captcha bằng RecaptchaSolver)
            success = register_apify_account(
                self.page, email, first_name, last_name, password
            )
            
            self._maybe_refresh_browser()
            return success
            
        except Exception as e:
            print(f"  [BROWSER] ❌ Lỗi đăng ký: {e}")
            # Thử tạo browser mới cho lần sau
            try:
                self.close()
                time.sleep(1)
                self._setup_browser()
            except:
                pass
            return False
    
    def close(self):
        """Đóng browser."""
        if self.page:
            try:
                self.page.quit()
            except:
                pass
            self.page = None


# ═══════════════════════════════════════════════════════════════════
# PHASE 2: HTTP Verify Email
# ═══════════════════════════════════════════════════════════════════

def verify_email_via_http(verify_link, proxy=None):
    """
    Click link verify email bằng HTTP GET (không cần browser).
    Nhanh hơn nhiều so với navigate browser qua proxy.
    
    Returns:
        bool: True nếu verify thành công
    """
    headers = {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }
    proxies = _make_proxy_dict(proxy)
    
    try:
        print(f"  [HTTP] GET verify link...")
        resp = requests.get(verify_link, headers=headers, proxies=proxies, 
                          timeout=15, allow_redirects=True)
        
        if resp.status_code == 200:
            body = resp.text.lower()
            if any(kw in body for kw in ["verified", "success", "dashboard", "welcome", "console"]):
                print(f"  [HTTP] ✅ Email verified thành công!")
                return True
            if "console.apify.com" in resp.url:
                print(f"  [HTTP] ✅ Redirected to console — verified!")
                return True
        
        # 3xx redirect → OK
        if resp.status_code in [301, 302]:
            print(f"  [HTTP] ✅ Verify redirected — OK!")
            return True
            
        print(f"  [HTTP] Verify response: HTTP {resp.status_code}")
        return resp.status_code < 400
        
    except Exception as e:
        print(f"  [HTTP] ❌ Lỗi verify: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════
# PHASE 3: HTTP Login + Get API Key (không cần browser!)
# ═══════════════════════════════════════════════════════════════════

def login_and_get_api_key_http(email, password, proxy=None):
    """
    Đăng nhập Apify và lấy API key hoàn toàn bằng HTTP.
    Thử nhiều phương pháp khác nhau.
    
    Returns:
        str: API key hoặc None
    """
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Accept": "application/json, text/plain, */*",
        "Origin": APIFY_BASE,
        "Referer": f"{APIFY_BASE}/sign-in",
        "User-Agent": _random_ua(),
    })
    
    proxies = _make_proxy_dict(proxy)
    if proxies:
        session.proxies.update(proxies)
    
    # ── Bước 1: Login ──
    login_payload = {
        "email": email.lower().strip(),
        "password": password,
    }
    
    try:
        print(f"  [HTTP] POST /auth/login...")
        resp = session.post(f"{APIFY_BASE}/auth/login", json=login_payload, 
                          timeout=15, allow_redirects=True)
        
        if resp.status_code not in [200, 201, 302]:
            print(f"  [HTTP] ⚠️ Login HTTP {resp.status_code}, thử không cần turnstile...")
            # Thử thêm vài variants
            for variant_url in [
                f"{APIFY_BASE}/api/auth/login",
                f"{APIFY_BASE}/auth/login",
            ]:
                try:
                    resp = session.post(variant_url, json=login_payload, timeout=10)
                    if resp.status_code in [200, 201]:
                        break
                except:
                    continue
        
        if resp.status_code in [200, 201]:
            print(f"  [HTTP] ✅ Login OK! (cookies: {len(session.cookies)})")
        elif resp.status_code == 302:
            print(f"  [HTTP] ✅ Login OK (redirect)")
        else:
            print(f"  [HTTP] ❌ Login failed: HTTP {resp.status_code}")
            try:
                print(f"         Response: {resp.text[:200]}")
            except: pass
            return None
            
    except Exception as e:
        print(f"  [HTTP] ❌ Login error: {e}")
        return None
    
    # ── Bước 2: Lấy API key ──
    api_key = _try_get_api_key(session)
    return api_key


def login_and_get_api_key_browser(page, email, password):
    """
    Fallback: Dùng browser đã mở để lấy API key.
    Ưu tiên lấy ngay trên Dashboard, nếu không có mới login.
    """
    try:
        # 1. 100% vào đúng dashboard gốc để tránh màn hình welcome hoặc bị cache
        print("  [BROWSER] Điều hướng đến trang chủ console.apify.com...")
        page.get("https://console.apify.com/")
        page.wait.load_start()
        time.sleep(3)
        
        body = page.ele('tag:body').text if page.ele('tag:body') else ""
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body)
        if keys:
            print(f"  [BROWSER] ✅ Lấy API key ngay trên Dashboard: {keys[0][:15]}...")
            return keys[0]
            
        # Thử lấy bằng cách click nút Copy trên Dashboard (nhờ bạn phát hiện HTML snippet)
        try:
            from DrissionPage.common import Keys
            copy_btn = page.ele('@data-test=api-tokens-item-copy', timeout=2)
            if copy_btn:
                copy_btn.click()
                time.sleep(0.5)
                
                # Tạo input ẩn để paste token từ clipboard
                page.run_js('var inp = document.createElement("input"); inp.id = "temp_token_input"; document.body.appendChild(inp);')
                inp = page.ele('#temp_token_input')
                inp.click()
                time.sleep(0.2)
                
                # Bấm Ctrl + V
                page.actions.key_down(Keys.CTRL).type('v').key_up(Keys.CTRL)
                time.sleep(0.5)
                
                val = inp.property('value')
                if val and "apify_api_" in val:
                    print(f"  [BROWSER] ✅ Đã copy API key thành công từ Dashboard: {val[:15]}...")
                    page.run_js('document.getElementById("temp_token_input").remove();')
                    return val.strip()
        except Exception as e:
            print(f"  [BROWSER] ⚠️ Không thể copy từ Dashboard: {e}")

        # 2. Nếu không thấy ở Dashboard, thử vào thẳng trang settings (vì session vẫn còn)
        print(f"  [BROWSER] Không thấy ở Dashboard, thử mở trang Settings...")
        page.get(f"{APIFY_BASE}/settings/integrations")
        time.sleep(3)
        
        try:
            reveal = page.ele('@data-test=toggle-visibility-button', timeout=2)
            if reveal:
                reveal.click()
                time.sleep(1)
        except: pass
        
        body = page.ele('tag:body').text if page.ele('tag:body') else ""
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body)
        if keys:
            print(f"  [BROWSER] ✅ Lấy API key ở Settings: {keys[0][:15]}...")
            return keys[0]
            
        # 3. Nếu vẫn không được (mất session), tiến hành Login lại
        print(f"  [BROWSER] Mất session, đang tiến hành đăng nhập lại...")
        page.get(f"{APIFY_BASE}/sign-in")
        page.wait.load_start()
        time.sleep(2)
        
        try:
            email_btn = page.ele('text:Continue with email', timeout=3) or \
                       page.ele('text:Sign in with email', timeout=2)
            if email_btn:
                email_btn.click()
                time.sleep(1)
        except: pass
        
        email_ele = page.ele('@name=email', timeout=5) or page.ele('@type=email', timeout=5)
        if email_ele:
            human_type(email_ele, email)
            time.sleep(0.5)
            
            next_btn = page.ele('xpath://button[@type="submit"]') or page.ele('button:has-text("Continue")')
            if next_btn:
                page.run_js('arguments[0].click();', next_btn)
                time.sleep(2)
        
        pw_ele = page.ele('@name=password', timeout=5) or page.ele('@type=password', timeout=5)
        if pw_ele:
            human_type(pw_ele, password)
            time.sleep(0.5)
            
            login_btn = page.ele('xpath://button[@type="submit"]') or page.ele('button:has-text("Sign in")')
            if login_btn:
                page.run_js('arguments[0].click();', login_btn)
                time.sleep(5)
        
        # Sau khi login, thử tìm ở Dashboard mới
        body = page.ele('tag:body').text if page.ele('tag:body') else ""
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body)
        if keys:
            print(f"  [BROWSER] ✅ Lấy API key trên Dashboard sau khi Login: {keys[0][:15]}...")
            return keys[0]
            
        # Nếu không có, vào Settings
        page.get(f"{APIFY_BASE}/settings/integrations")
        time.sleep(3)
        body = page.ele('tag:body').text if page.ele('tag:body') else ""
        keys = re.findall(r'apify_api_[a-zA-Z0-9]+', body)
        if keys:
            print(f"  [BROWSER] ✅ Found API key in Settings: {keys[0][:15]}...")
            return keys[0]
        
        print(f"  [BROWSER] ⚠️ No API key found on page")
        return None
        
    except Exception as e:
        print(f"  [BROWSER] ❌ Error: {e}")
        return None


def _try_get_api_key(session):
    """Thử nhiều cách để lấy API key từ session đã login."""
    
    # Method 1: /v2/users/me
    try:
        print(f"  [HTTP] GET /v2/users/me...")
        resp = session.get(f"{APIFY_API_BASE}/users/me", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            key = _find_api_key_in_dict(data)
            if key:
                print(f"  [HTTP] ✅ API key from /users/me: {key[:15]}...")
                return key
    except Exception as e:
        print(f"  [HTTP] /users/me failed: {e}")
    
    # Method 2: Settings page HTML
    try:
        print(f"  [HTTP] GET /settings/integrations...")
        resp = session.get(f"{APIFY_BASE}/settings/integrations", timeout=10)
        if resp.status_code == 200:
            keys = re.findall(r'apify_api_[a-zA-Z0-9]+', resp.text)
            if keys:
                print(f"  [HTTP] ✅ API key from settings: {keys[0][:15]}...")
                return keys[0]
    except Exception as e:
        print(f"  [HTTP] Settings failed: {e}")
    
    # Method 3: Thử các API endpoints khác
    try:
        for endpoint in [
            f"{APIFY_API_BASE}/users/me/api-tokens",
            f"{APIFY_BASE}/api/v2/users/me",
        ]:
            resp = session.get(endpoint, timeout=8)
            if resp.status_code == 200:
                keys = re.findall(r'apify_api_[a-zA-Z0-9]+', resp.text)
                if keys:
                    print(f"  [HTTP] ✅ API key found: {keys[0][:15]}...")
                    return keys[0]
    except:
        pass
    
    print(f"  [HTTP] ⚠️ Không tìm thấy API key qua HTTP")
    return None


# ═══════════════════════════════════════════════════════════════════
# Full Pipeline
# ═══════════════════════════════════════════════════════════════════

def full_hybrid_pipeline(email, mailtm_password, apify_password, 
                         first_name, last_name, registrar, proxy=None):
    """
    Pipeline đầy đủ:
      1. Browser (no proxy) → đăng ký account + xử lý captcha
      2. HTTP → chờ verify email + click link
      3. HTTP → login + lấy API key
      4. Fallback: browser → login + lấy API key (nếu HTTP fail)
    
    Args:
        registrar: HybridRegistrar instance (shared browser)
        proxy: Proxy string cho HTTP requests
    
    Returns:
        str: API key hoặc None
    """
    from auto_verify import get_inbox_mailtm, get_message_content_mailtm
    
    # ── Phase 1: Đăng ký bằng browser (KHÔNG proxy) ──
    print("\n  [PHASE 1] Đăng ký tài khoản (browser trực tiếp)...")
    success = registrar.register_account(email, first_name, last_name, apify_password)
    
    if not success:
        print("  ❌ Đăng ký thất bại.")
        return None
    
    print("  ✅ Đăng ký thành công!")
    
    # ── Phase 2: Chờ email verify + click link ──
    print("\n  [PHASE 2] Chờ email xác nhận từ Apify...")
    verify_link = _wait_for_verify_email(email, mailtm_password)
    
    if not verify_link:
        print("  ❌ Không nhận được email xác nhận sau 30s")
        # Vẫn thử lấy API key — có thể account đã auto-verify
    else:
        print(f"  ✅ Tìm thấy link verify!")
        print("  [WAIT] Đợi 5s cho hệ thống Apify xử lý email...")
        time.sleep(5)
        
        # Dùng trực tiếp browser (không proxy) cho nhanh, bỏ qua HTTP request chậm
        print("  [VERIFY] Truy cập link verify bằng browser (siêu tốc)...")
        try:
            registrar.page.get(verify_link)
            registrar.page.wait.load_start()
            time.sleep(3)
            print("  ✅ Đã verify xong bằng browser!")
        except Exception as e:
            print(f"  ⚠️ Lỗi verify bằng browser: {e}")
    
    # ── Phase 3: Login + lấy API key ──
    print("\n  [PHASE 3] Lấy API key...")
    
    api_key = None
    
    # Do proxy free hay bị timeout (15s) khi POST tới Apify,
    # chúng ta sẽ ưu tiên dùng luôn browser (đã mở sẵn, không proxy) để lấy key cho lẹ.
    print("  [BROWSER] Lấy API key trực tiếp qua browser...")
    api_key = login_and_get_api_key_browser(
        registrar.page, email, apify_password
    )
    
    if not api_key:
        print("  [FALLBACK] Browser không lấy được, thử HTTP proxy...")
        api_key = login_and_get_api_key_http(email, apify_password, proxy=proxy)
    
    return api_key


def _wait_for_verify_email(email, mailtm_password, max_wait=30):
    """Chờ email verify từ Apify và trả về link verify."""
    from auto_verify import get_inbox_mailtm, get_message_content_mailtm
    
    for attempt in range(max_wait // 2):
        inbox, token = get_inbox_mailtm(email, mailtm_password)
        if inbox:
            inbox_str = json.dumps(inbox).lower()
            if "apify" in inbox_str:
                messages = inbox.get("hydra:member", [])
                for msg in messages:
                    if isinstance(msg, dict):
                        subject = msg.get("subject", "").lower()
                        if any(kw in subject for kw in ["verify", "confirm", "action required", "email"]):
                            message_id = msg.get("id") or msg.get("messageID")
                            if message_id:
                                content = get_message_content_mailtm(message_id, token)
                                if content:
                                    if isinstance(content, list):
                                        content = " ".join(str(c) for c in content)
                                    elif not isinstance(content, str):
                                        content = str(content)
                                    
                                    links = re.findall(
                                        r'(https://[a-zA-Z0-9\-\.]*apify\.com[^\s\"\'\>]+)', 
                                        content
                                    )
                                    for l in links:
                                        l = l.replace('\\/', '/')
                                        if 'verify' in l.lower() or 'confirm' in l.lower():
                                            return l
        time.sleep(2)
    
    return None


# ═══════════════════════════════════════════════════════════════════
# Utility Functions
# ═══════════════════════════════════════════════════════════════════

def _random_ua():
    agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    ]
    return random.choice(agents)


def _make_proxy_dict(proxy_str):
    if not proxy_str:
        return None
    if not proxy_str.startswith("http"):
        proxy_str = f"http://{proxy_str}"
    return {"http": proxy_str, "https": proxy_str}


def _find_api_key_in_dict(d, depth=0):
    """Recursively search for apify_api_ key in a nested dict."""
    if depth > 5:
        return None
    if isinstance(d, str):
        if d.startswith("apify_api_"):
            return d
        return None
    if isinstance(d, dict):
        for k, v in d.items():
            result = _find_api_key_in_dict(v, depth + 1)
            if result:
                return result
    if isinstance(d, list):
        for item in d:
            result = _find_api_key_in_dict(item, depth + 1)
            if result:
                return result
    return None
