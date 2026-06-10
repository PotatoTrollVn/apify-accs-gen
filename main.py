"""
main_http.py — Hybrid Pipeline: Browser đăng ký + HTTP lấy key.

Cách hoạt động:
  1. Browser (KHÔNG proxy) → mở signup → fill form → captcha → đăng ký
     → Trang load nhanh vì không qua proxy, captcha xử lý tự nhiên
  2. HTTP Request → verify email link (nhẹ, nhanh)
  3. HTTP Request → login + lấy API key (không cần navigate browser)
  4. Fallback: Browser → login + lấy key (nếu HTTP fail)

So với main.py cũ:
  - Không timeout khi load trang (không proxy cho browser)
  - Lấy API key nhanh hơn 3-5x nhờ HTTP thay vì browser navigate

Usage:
  python main_http.py [số_account]
  python main_http.py 5
"""
import os
import sys
import time
import json
import random

from generate_email import create_mailtm_accounts, get_domains
from auto_register import generate_fake_name, generate_random_password
from api_register import HybridRegistrar, full_hybrid_pipeline

# Import ProxyManager from root directory
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proxy_manager import ProxyManager

# ---------- CONFIGURATION ----------
CONFIG_FILE = "apify_config.json"
ACCOUNTS_FILE = "registered_accounts.json"
VERIFIED_OUTPUT = "apify_token.json"


def main():
    print("══════════════════════════════════════════════════")
    print("  APIFY ACCOUNT CREATOR — HYBRID MODE")
    print("  Browser đăng ký (no proxy) • HTTP lấy key (proxy)")
    print("══════════════════════════════════════════════════")

    # ── Load config ──
    gemini_key = None
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                conf = json.load(f)
                gemini_key = conf.get("gemini_api_key")
    except:
        pass

    # ── Load proxies (chỉ dùng cho HTTP requests, không cho browser) ──
    print("\n[INIT] Đang tải proxy (chỉ dùng cho HTTP requests)...")
    cache_dir = os.path.dirname(os.path.abspath(__file__))
    pm = ProxyManager(gemini_api_key=gemini_key, cache_dir=cache_dir)
    pm.load_and_validate_proxies()

    use_proxy = bool(pm.valid_proxies)
    if not use_proxy:
        print("[INFO] Không có proxy — HTTP requests sẽ dùng IP thật.")
        print("       Browser luôn dùng IP thật (không ảnh hưởng).")

    # ── Parse args ──
    try:
        num_accounts = int(sys.argv[1]) if len(sys.argv) > 1 else 100
    except:
        num_accounts = 100

    # ── Get email domain ──
    domains = get_domains()
    if not domains:
        print("[ERROR] Không lấy được domain từ Mail.tm.")
        return
    domain = domains[0]
    print(f"[INIT] Mail.tm domain: @{domain}")

    # ── Load existing keys ──
    try:
        with open(VERIFIED_OUTPUT, "r", encoding="utf-8") as f:
            verified_keys = json.load(f).get("apify_api_keys", [])
    except:
        verified_keys = []

    print(f"[INIT] Đã có {len(verified_keys)} API keys.")

    # ── Init hybrid registrar (browser KHÔNG proxy) ──
    print("\n[INIT] Khởi tạo Browser (không proxy — load nhanh)...")
    registrar = HybridRegistrar()

    # ── Stats ──
    stats = {"total": 0, "success": 0, "fail_register": 0, 
             "fail_verify": 0, "fail_key": 0}

    try:
        for i in range(num_accounts):
            stats["total"] += 1
            print(f"\n{'═'*55}")
            print(f"  [{i+1}/{num_accounts}] TẠO TÀI KHOẢN MỚI (Hybrid Mode)")
            print(f"{'═'*55}")

            # ── 1. Tạo email ──
            print("\n  [BƯỚC 1] Tạo Email ảo...")
            created = create_mailtm_accounts(domain, 1)
            if not created:
                print("  ⚠️ Không thể tạo email. Bỏ qua.")
                continue

            email, mailtm_pw = list(created.items())[0]
            first, last = generate_fake_name()
            apify_pw = generate_random_password()

            # ── Chọn proxy cho HTTP requests ──
            current_proxy = None
            if use_proxy:
                current_proxy = pm.get_proxy(prefer_tier='S') or pm.get_proxy()
                if current_proxy:
                    proxy_info = pm.get_proxy_info(current_proxy)
                    tier = f"Tier {proxy_info['tier']}" if proxy_info else "?"
                    print(f"  [PROXY] HTTP requests dùng: {current_proxy} [{tier}]")

            # ── 2. Full pipeline ──
            api_key = full_hybrid_pipeline(
                email=email,
                mailtm_password=mailtm_pw,
                apify_password=apify_pw,
                first_name=first,
                last_name=last,
                registrar=registrar,
                proxy=current_proxy,
            )

            if api_key:
                stats["success"] += 1
                if use_proxy and current_proxy:
                    pm.report_proxy_success(current_proxy)

                if api_key not in verified_keys:
                    verified_keys.append(api_key)
                    with open(VERIFIED_OUTPUT, "w", encoding="utf-8") as f:
                        json.dump({"apify_api_keys": verified_keys}, f, indent=4)
                    print(f"\n  🎉 API key lưu thành công: {api_key[:15]}...")
                else:
                    print(f"\n  [INFO] API key đã tồn tại.")
            else:
                if use_proxy and current_proxy:
                    pm.report_proxy_failure(current_proxy)
                print(f"\n  ❌ Không lấy được API key.")

            # Delay
            delay = random.uniform(5, 10)
            print(f"\n  [WAIT] Chờ {delay:.1f}s...")
            time.sleep(delay)

    except KeyboardInterrupt:
        print("\n\n[STOP] Dừng bởi người dùng (Ctrl+C)")
    finally:
        registrar.close()

    # ── Summary ──
    print(f"\n{'═'*55}")
    print(f"  KẾT QUẢ PHIÊN CHẠY")
    print(f"{'═'*55}")
    print(f"  Tổng thử:          {stats['total']}")
    print(f"  ✅ Thành công:      {stats['success']}")
    print(f"  ❌ Thất bại:        {stats['total'] - stats['success']}")
    rate = stats['success'] / max(1, stats['total']) * 100
    print(f"  📊 Tỷ lệ:          {rate:.1f}%")
    print(f"  🔑 Tổng API keys:  {len(verified_keys)}")
    print(f"{'═'*55}")

    if use_proxy:
        pm.print_session_summary()

    print(f"\n🎉 Hoàn tất tạo {stats['success']} tài khoản! Tokens tại: {VERIFIED_OUTPUT}")

    # ── Tự động chạy Check API Tokens ──
    print(f"\n{'═'*55}")
    print("  TỰ ĐỘNG KIỂM TRA LẠI CÁC API KEY...")
    print(f"{'═'*55}")
    try:
        import subprocess
        parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        check_script = os.path.join(parent_dir, "check_apify_tokens.py")
        if os.path.exists(check_script):
            # Run the checker from the current directory (apify_account_creator) so it checks the local apify_token.json
            subprocess.run([sys.executable, check_script], cwd=os.path.dirname(os.path.abspath(__file__)))
        else:
            print(f"  [CẢNH BÁO] Không tìm thấy script {check_script}")
    except Exception as e:
        print(f"  [ERROR] Lỗi khi tự động chạy check_apify_tokens: {e}")

if __name__ == "__main__":
    main()
