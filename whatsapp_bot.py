import sys
import time
import argparse
import pywhatkit as kit

def build_parser():
    parser = argparse.ArgumentParser(description='Temporary WhatsApp Broadcast Bot')
    parser.add_argument('--url', type=str, required=True, help='The Survey URL to send')
    parser.add_argument('--numbers', type=str, required=True, help='Comma separated list of phone numbers')
    return parser

import webbrowser
_original_open = webbrowser.open

def _force_chrome_open(url, new=0, autoraise=True):
    chrome_paths = [
        "C:/Program Files/Google/Chrome/Application/chrome.exe %s",
        "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe %s"
    ]
    for path in chrome_paths:
        try:
            return webbrowser.get(path).open(url, new=new, autoraise=autoraise)
        except Exception:
            pass
    return _original_open(url, new=new, autoraise=autoraise)

# Monkeypatch webbrowser.open globally so pywhatkit uses it
webbrowser.open = _force_chrome_open

def send_whatsapp_broadcast(phone_numbers, message):
    print("\n" + "="*50)
    print("WHATSAPP AUTOMATION BOT INITIATED")
    print("="*50)
    print(f"Total numbers to process: {len(phone_numbers)}")
    print("!!! WARNING !!!")
    print("Do NOT use your mouse or keyboard while the bot is running.")
    print("Ensure you are logged into WhatsApp Web on your default browser before continuing.")
    print("="*50)
    
    for i in range(5, 0, -1):
        print(f"Bot taking control in {i} seconds...", end="\r")
        time.sleep(1)
    print("\nStarting broadcast now...\n")
    
    for i, number in enumerate(phone_numbers):
        number = number.strip()
        if not number.startswith("+"):
            if len(number) == 10 and number.isdigit():
                print(f"[{i+1}/{len(phone_numbers)}] ℹ️ Auto-adding +91 country code to {number}")
                number = "+91" + number
            else:
                print(f"[{i+1}/{len(phone_numbers)}] ⚠️ Skipping {number} - Must include country code starting with '+'")
                continue
            
        print(f"[{i+1}/{len(phone_numbers)}] 📡 Preparing message for {number}...")
        try:
            import pyautogui
            # kit opens the browser, types the message, but sometimes fails to hit send.
            # We set tab_close=False so we can manually ensure it's sent.
            kit.sendwhatmsg_instantly(number, message, wait_time=25, tab_close=False)
            print(f"[{i+1}/{len(phone_numbers)}] 🔄 Typing message... enforcing send...")
            time.sleep(2)
            pyautogui.press("enter")
            time.sleep(4)
            pyautogui.hotkey("ctrl", "w") # close tab manually
            print(f"[{i+1}/{len(phone_numbers)}] ✅ Successfully sent to {number}")
            
            if i < len(phone_numbers) - 1:
                print("Waiting 10 seconds before next message to simulate human behavior...")
                time.sleep(10)
                
        except Exception as e:
            print(f"[{i+1}/{len(phone_numbers)}] ❌ Failed to send to {number}: {str(e)}")
            
    print("\n✅ Broadcast complete! You can safely use your computer again.")

if __name__ == "__main__":
    parser = build_parser()
    args = parser.parse_args()
    
    parts = [n.strip() for n in args.numbers.split(",") if n.strip()]
    if not parts:
        print("Error: No valid phone numbers provided.")
        sys.exit(1)
        
    msg = f"Hello! We would love your quick feedback. Please take a minute to fill out our new survey here:\n\n{args.url}"
    
    send_whatsapp_broadcast(parts, msg)
