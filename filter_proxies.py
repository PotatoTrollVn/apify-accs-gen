"""
filter_proxies.py — Script chạy riêng để lọc và đánh giá chất lượng proxy.

Chạy: python filter_proxies.py [--force]

Flags:
  --force   Bỏ qua cache, fetch và test lại từ đầu.

Output:
  - In bảng kết quả chi tiết proxy (IP, Latency, Success Rate, Score, Tier)
  - Lưu kết quả vào proxy_cache.json
"""
import os
import sys
import time

# Add parent directory to path so we can import proxy_manager
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proxy_manager import ProxyManager

# Try to load gemini key from apify_config.json
import json
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "apify_config.json")


def main():
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║         PROXY QUALITY FILTER & ANALYZER                     ║")
    print("║         Lọc và đánh giá proxy tốt nhất                      ║")
    print("╚══════════════════════════════════════════════════════════════╝")
    print()

    force_refresh = "--force" in sys.argv

    # Load Gemini API key if available
    gemini_key = None
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                conf = json.load(f)
                gemini_key = conf.get("gemini_api_key")
    except Exception:
        pass

    # Cache directory = this script's directory (apify_account_creator/)
    cache_dir = os.path.dirname(os.path.abspath(__file__))

    pm = ProxyManager(gemini_api_key=gemini_key, cache_dir=cache_dir)

    start_time = time.time()

    if force_refresh:
        print("[MODE] Force refresh — bỏ qua cache, fetch và test lại từ đầu.\n")

    pm.load_and_validate_proxies(force_refresh=force_refresh)

    elapsed = time.time() - start_time

    if not pm.valid_proxies:
        print("\n❌ Không tìm thấy proxy hợp lệ nào!")
        print("   Hãy kiểm tra kết nối mạng hoặc thử lại sau.")
        return

    # Print full detailed report
    pm.print_full_report()

    # Tier breakdown
    if pm.proxy_scores:
        tier_s = [p for p, info in pm.proxy_scores.items() if info.get("tier") == "S"]
        tier_a = [p for p, info in pm.proxy_scores.items() if info.get("tier") == "A"]
        tier_b = [p for p, info in pm.proxy_scores.items() if info.get("tier") == "B"]

        # Recommendations
        print("┌─────────────────────────────────────────────────────────────┐")
        print("│                      KHUYẾN NGHỊ                            │")
        print("├─────────────────────────────────────────────────────────────┤")

        if tier_s:
            print(f"│  ⭐ Có {len(tier_s)} proxy Tier S — Tuyệt vời cho Apify!            │")
            best = sorted(pm.proxy_scores.items(), key=lambda x: x[1]["score"], reverse=True)[0]
            print(f"│  🏆 Proxy tốt nhất: {best[0]:<20} score={best[1]['score']:.3f}     │")
        elif tier_a:
            print(f"│  🔵 Có {len(tier_a)} proxy Tier A — Tạm ổn, nên chạy lại sau.       │")
        else:
            print(f"│  ⚠️  Chỉ có proxy Tier B — Chất lượng thấp, cần nguồn khác.  │")

        apify_reachable = [
            p for p, info in pm.proxy_scores.items()
            if info.get("apify_reachable")
        ]
        print(f"│  🌐 {len(apify_reachable)}/{len(pm.proxy_scores)} proxy truy cập được Apify.com          │")
        print("└─────────────────────────────────────────────────────────────┘")

    print(f"\n⏱️  Hoàn tất trong {elapsed:.1f} giây.")
    print(f"📁 Kết quả đã được lưu vào: {os.path.join(cache_dir, 'proxy_cache.json')}")
    print(f"\n💡 Tip: Chạy 'python main.py' để tạo account Apify với proxy đã lọc.")
    print(f"💡 Tip: Chạy 'python filter_proxies.py --force' để bỏ qua cache.")


if __name__ == "__main__":
    main()
