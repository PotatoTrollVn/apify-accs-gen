import json
import time
import random
import string
import sys
import os
from DrissionPage import ChromiumPage, ChromiumOptions
from GoogleRecaptchaBypass.RecaptchaSolver import RecaptchaSolver

if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

CONFIG_FILE = "apify_config.json"
OUTPUT_FILE = "registered_accounts.json"

def load_generated_emails():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("generated_emails", []), data.get("mailtm_passwords", {})
    except Exception:
        return [], {}

def load_existing_accounts():
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_accounts(accounts):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(accounts, f, indent=4, ensure_ascii=False)
    print(f"  [SAVE] {len(accounts)} accounts -> {OUTPUT_FILE}")

def generate_random_password(length=14):
    lower = string.ascii_lowercase
    upper = string.ascii_uppercase
    digits = string.digits
    special = "!@#$%^&*"
    password = [random.choice(lower), random.choice(upper), random.choice(digits), random.choice(special)]
    all_chars = lower + upper + digits + special
    password += [random.choice(all_chars) for _ in range(length - 4)]
    random.shuffle(password)
    return "".join(password)

def generate_fake_name():
    first_names = ["James", "Mary", "John", "Patricia", "Robert", "Jennifer", "Michael", "Linda"]
    last_names = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis"]
    return random.choice(first_names), random.choice(last_names)

def human_type(ele, text):
    if not ele: return
    ele.clear()
    for char in text:
        ele.input(char)
        time.sleep(random.uniform(0.01, 0.05))
    time.sleep(random.uniform(0.1, 0.3))

def register_apify_account(page, email, first_name, last_name, password):
    try:
        print(f"  [NAVIGATE] https://console.apify.com/sign-up")
        page.get("https://console.apify.com/sign-up")
        page.wait.load_start()
        time.sleep(2)

        try:
            email_btn = page.ele('text:Continue with email', timeout=10)
            if email_btn:
                email_btn.click()
                time.sleep(1)
        except: pass
            
        try:
            email_btn2 = page.ele('text:Sign up with email', timeout=10)
            if email_btn2:
                email_btn2.click()
                time.sleep(1)
        except: pass

        try:
            btn = page.ele('button:has-text("Accept all")', timeout=3) or page.ele('button:has-text("Allow all")', timeout=3)
            if btn: btn.click(); time.sleep(0.5)
        except: pass

        time.sleep(random.uniform(0.5, 1.5))
        
        email_ele = page.ele('@name=email', timeout=15) or page.ele('@type=email', timeout=15)
        if email_ele:
            print(f"  [FILL] Email: {email}")
            human_type(email_ele, email)
            time.sleep(random.uniform(0.5, 1.0))
            
            # Thay vì tìm nút bấm dễ nhầm lẫn, nhấn ENTER trực tiếp tại ô email để qua bước Password
            print("  [ACTION] Pressing ENTER to continue...")
            email_ele.input('\n')
            time.sleep(random.uniform(2.0, 3.0))

        pw_ele = page.ele('@name=password', timeout=15) or page.ele('@id=password', timeout=15) or page.ele('@type=password', timeout=15)
        if pw_ele:
            print(f"  [FILL] Password: {password}")
            human_type(pw_ele, password)
            time.sleep(random.uniform(0.5, 1.0))
            
        uname_ele = page.ele('@name=username', timeout=0.5)
        if uname_ele:
            print(f"  [FILL] Username: {first_name.lower()}{random.randint(10,999)}")
            human_type(uname_ele, f"{first_name.lower()}{random.randint(10,999)}")
            
        fullname_ele = page.ele('@name=fullName', timeout=0.5) or page.ele('@name=name', timeout=0.5) or page.ele('@placeholder=Full name', timeout=0.5)
        if fullname_ele:
            print(f"  [FILL] Full name: {first_name} {last_name}")
            human_type(fullname_ele, f"{first_name} {last_name}")
            
        first_ele = page.ele('@name=firstName', timeout=0.5)
        if first_ele:
            print(f"  [FILL] First name: {first_name}")
            human_type(first_ele, first_name)
            
        last_ele = page.ele('@name=lastName', timeout=0.5)
        if last_ele:
            print(f"  [FILL] Last name: {last_name}")
            human_type(last_ele, last_name)

        time.sleep(0.5)

        try:
            tos_checkboxes = page.eles('css:input[type="checkbox"]')
            for cb in tos_checkboxes:
                page.run_js('arguments[0].click();', cb)
                time.sleep(0.2)
        except: pass

        print("  [SUBMIT] Pressing ENTER to sign up...")
        if pw_ele:
            pw_ele.input('\n')
        else:
            # Fallback nếu không có ô password (hiếm)
            submit_btn = page.ele('xpath://button[@type="submit"]') or page.ele('button:has-text("Sign up")')
            if submit_btn:
                page.run_js('arguments[0].click();', submit_btn)

        print("  [WAIT] Waiting for response or reCaptcha...")
        time.sleep(5)
        
        # Handle reCAPTCHA via DrissionPage RecaptchaSolver
        try:
            iframe = page.ele("xpath://iframe[contains(@title, 'recaptcha')]", timeout=3)
            if iframe and iframe.states.is_displayed:
                print("  [CAPTCHA] reCAPTCHA challenge appeared, attempting to solve...")
                solver = RecaptchaSolver(page)
                solver.solveCaptcha()
                print("  [CAPTCHA] ✅ reCAPTCHA solved!")
                
                # Re-submit if needed
                time.sleep(2)
                if submit_btn and submit_btn.states.is_displayed:
                    page.run_js('arguments[0].click();', submit_btn)
        except Exception as e:
            print(f"  [CAPTCHA] No reCAPTCHA challenge detected or error: {e}")

        for elapsed in range(120):
            try:
                url = page.url.lower()
                body = page.html.lower()
                
                # Handle "Welcome to Apify" onboarding screen if it appears
                try:
                    fn_ele = page.ele('@data-test=name-input', timeout=0.5) or page.ele('css:input#name', timeout=0.5)
                    if fn_ele and fn_ele.states.is_displayed:
                        print("  [ONBOARDING] 'Welcome to Apify' screen detected.")
                        print(f"  [FILL] Full name: {first_name} {last_name}")
                        fn_ele.clear()
                        fn_ele.input(f"{first_name} {last_name}")
                        time.sleep(0.5)
                        
                        c_btn = page.ele('button:has-text("Continue")', timeout=1) or page.ele('xpath://button[@type="submit"]')
                        if c_btn:
                            print("  [ACTION] Clicking Continue...")
                            page.run_js('arguments[0].click();', c_btn)
                            time.sleep(2)
                        continue
                except: pass
                    
                if "verify" in body or "check your inbox" in body or "confirm" in body:
                    print("  ✅ SUCCESS! Verification message detected.")
                    return True
                if "already exists" in body or "already in use" in body:
                    print("  ⚠️ Email already registered.")
                    return False
                if "dashboard" in url or "console.apify.com/?welcome" in url:
                    print("  ✅ SUCCESS! Reached dashboard.")
                    return True
            except: pass
            time.sleep(1)
            
        return False
    except Exception as e:
        print(f"  [ERROR] {e}")
        return False

def run_registration():
    emails, mailtm_passwords = load_generated_emails()
    if not emails:
        print("[ABORT] No emails found. Please generate them first.")
        return

    existing = load_existing_accounts()
    done_emails = {a["email"] for a in existing}
    
    todo = [e for e in emails if e not in done_emails]
        
    if not todo:
        print("[INFO] All accounts have been registered.")
        return

    accounts = list(existing)

    print(f"\n==================================================")
    print(f"BẮT ĐẦU ĐĂNG KÝ TỰ ĐỘNG TÀI KHOẢN APIFY")
    print(f"==================================================")

    for idx, email in enumerate(todo, 1):
        print(f"\n{'='*50}\n[{idx}/{len(todo)}] {email}\n{'='*50}")
        co = ChromiumOptions()
        co.auto_port()
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.incognito(True)
        
        page = ChromiumPage(co)
        try:
            first, last = generate_fake_name()
            pw = generate_random_password()
            user = f"{first.lower()}_{last.lower()}_{random.randint(10,99)}"

            success = register_apify_account(page, email, first, last, pw)
            
            if success:
                account_data = {
                    "username": user, "email": email, "password": pw,
                    "first_name": first, "last_name": last, 
                    "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
                }
                if email in mailtm_passwords:
                    account_data["mailtm_password"] = mailtm_passwords[email]
                    
                accounts.append(account_data)
                save_accounts(accounts)
                time.sleep(1)
            else:
                print("\n  [🚨 CẢNH BÁO] Đăng ký thất bại cho tài khoản này.")
        finally:
            page.quit()

if __name__ == "__main__":
    run_registration()
