import requests
import string
import random
import json
import sys

if sys.platform.startswith('win'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def get_domains():
    try:
        r = requests.get('https://api.mail.tm/domains', timeout=10)
        domains = r.json().get('hydra:member', [])
        return [d['domain'] for d in domains]
    except:
        return []

def create_mailtm_accounts(domain, count=1):
    created = {}
    for i in range(count):
        address = ''.join(random.choices(string.ascii_lowercase, k=10)) + '@' + domain
        password = 'Password123!'
        payload = {'address': address, 'password': password}
        try:
            res = requests.post('https://api.mail.tm/accounts', json=payload, timeout=10)
            if res.status_code in [200, 201]:
                created[address] = password
                print(f"  [+] Đã tạo: {address}")
        except Exception as e:
            print(f"  [!] Lỗi tạo email: {e}")
    return created

def generate_mailtm_emails(count=10):
    print("Đang lấy danh sách domain từ Mail.tm...")
    domains = get_domains()
    if not domains:
        print("Không lấy được domain từ Mail.tm")
        return
    domain = domains[0]
    print(f"Sử dụng domain: @{domain}")
    
    print(f"Đang tạo {count} tài khoản Temp Mail...")
    created = create_mailtm_accounts(domain, count)
    
    if created:
        config = {
            "generated_emails": list(created.keys()),
            "mailtm_passwords": created
        }
        with open("apify_config.json", "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print("Đã lưu danh sách ra file apify_config.json thành công!")

if __name__ == "__main__":
    generate_mailtm_emails(10)
