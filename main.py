import json
import base64
import urllib.parse
import hmac
import hashlib
import time
import random
import requests
import threading
import asyncio
import telebot
import aiohttp

API_TOKEN = "8689418183:AAFAum43rNBCK64nzZ4Kn-7Cof3QkatplJo" # add bot token via @botfather
bot = telebot.TeleBot(API_TOKEN)

user_sessions = {}

def generate_signature_data(payload, user_key, data_key):
    payload_str = json.dumps(payload, separators=(',', ':'))
    a = base64.b64encode(payload_str.encode('utf-8')).decode('utf-8')
    
    ts = str(payload['t'])
    u = base64.b64encode(ts.encode('utf-8')).decode('utf-8')
    
    hmac_key = data_key[4:18].encode('utf-8')
    
    message = f"{u}.{a}".encode('utf-8')
    h = hmac.new(hmac_key, message, hashlib.sha256)
    hex_sig = h.hexdigest()
    f = base64.b64encode(hex_sig.encode('utf-8')).decode('utf-8')
    
    m = random.randint(1, 6)
    k = random.randint(2, 8)
    
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    h_rand = "".join(random.choice(alphabet) for _ in range(k))
    
    g = f"{k}{m}{f[0:m]}{h_rand}{f[m:]}"
    
    u_encoded = urllib.parse.quote_plus(u)
    a_encoded = urllib.parse.quote_plus(a)
    g_encoded = urllib.parse.quote_plus(g)
    
    return f"userKey={user_key}&data={u_encoded}.{a_encoded}.{g_encoded}"

def decrypt_response(encrypted_resp):
    try:
        decoded = base64.b64decode(encrypted_resp).decode('utf-8')
        return json.loads(decoded), True
    except Exception as e:
        return {"error": f"Failed to decrypt: {e}", "raw": encrypted_resp}, False

def make_request(session, url, payload, user_key, data_key, access_token=None):
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "*/*",
        "accept-language": "en,en-GB;q=0.9,en-US;q=0.8",
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": "https://discoverworldblends.in/",
        "origin": "https://discoverworldblends.in"
    }
    
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    
    post_data = generate_signature_data(payload, user_key, data_key)
    api_url = f"{url}?t={int(time.time() * 1000)}"
    
    try:
        response = session.post(api_url, data=post_data, headers=headers)
        
        if response.status_code == 200:
            res_json = response.json()
            if 'resp' in res_json:
                decrypted, success = decrypt_response(res_json['resp'])
                if success:
                    return decrypted
                else:
                    return res_json
            else:
                return res_json
        else:
            return {"error": f"HTTP {response.status_code}", "text": response.text}
    except Exception as e:
        return {"error": f"Request failed: {e}"}

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    chat_id = message.chat.id
    user_sessions[chat_id] = {
        "state": "AWAITING_MOBILE",
        "session": requests.Session(),
        "user_key": None,
        "data_key": None,
        "access_token": None,
        "mobile": None,
        "name": None
    }
    welcome_text = "<b>Enter Number:</b>"
    bot.reply_to(message, welcome_text, parse_mode="HTML")

@bot.message_handler(commands=['status'])
def show_status(message):
    chat_id = message.chat.id
    session_data = user_sessions.get(chat_id)
    if not session_data:
        bot.reply_to(message, "<b>No active session found. Send /start to begin.</b>", parse_mode="HTML")
        return
        
    is_auth = "Authenticated" if session_data.get('access_token') else "Not Authenticated"
    status_text = (
        f"<b>Current Session Status:</b>\n\n"
        f"<b>Random Name: {session_data.get('name') or 'N/A'}</b>\n"
        f"<b>Mobile: {session_data.get('mobile') or 'N/A'}</b>\n"
        f"<b>Pincode: 110001 (Delhi)</b>\n"
        f"<b>User Key: {session_data.get('user_key') or 'N/A'}</b>\n"
        f"<b>Auth Status: {is_auth}</b>"
    )
    bot.reply_to(message, status_text, parse_mode="HTML")

def _sync_update_progress_message(chat_id, force=False):
    session_data = user_sessions.get(chat_id)
    if not session_data or not session_data.get('progress_msg_id'):
        return
        
    now = time.time()
    if not force and (now - session_data.get('last_edit_time', 0) < 1.5):
        return
        
    session_data['last_edit_time'] = now
    
    txt = (
        f"<b>Spinning in progress...</b>\n\n"
        f"<b>Total Spins: {session_data['total_spins']} / 30000</b>\n"
        f"<b>Won Rewards: {session_data['won_rewards']} </b>"
    )
    try:
        bot.edit_message_text(
            chat_id=chat_id,
            message_id=session_data['progress_msg_id'],
            text=txt,
            parse_mode="HTML"
        )
    except Exception:
        pass

async def update_progress_message(chat_id, force=False):
    await asyncio.to_thread(_sync_update_progress_message, chat_id, force)

async def spin_worker(chat_id, client, lock):
    session_data = user_sessions.get(chat_id)
    if not session_data:
        return
        
    spin_url = f"https://discoverworldblends.in/api/users/getReward/{session_data['user_key']}"
    headers = {
        "content-type": "application/x-www-form-urlencoded; charset=UTF-8",
        "accept": "*/*",
        "accept-language": "en,en-GB;q=0.9,en-US;q=0.8",
        "priority": "u=1, i",
        "sec-ch-ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "referer": "https://discoverworldblends.in/",
        "origin": "https://discoverworldblends.in",
        "Authorization": f"Bearer {session_data['access_token']}"
    }
    
    while True:
        async with lock:
            if session_data['total_spins'] >= 30000:
                break
            session_data['total_spins'] += 1
            current_spin = session_data['total_spins']
            
        payload = {
            "userKey": session_data['user_key'],
            "t": int(time.time() * 1000)
        }
        post_data = generate_signature_data(payload, session_data['user_key'], session_data['data_key'])
        api_url = f"{spin_url}?t={int(time.time() * 1000)}"
        
        try:
            async with client.post(api_url, data=post_data, headers=headers) as response:
                raw_text = await response.text()
                
                if response.status == 401 or response.status == 400:
                    async with lock:
                        session_data['total_spins'] = 30000
                    
                    try:
                        res_json = json.loads(raw_text)
                        resp_obj = res_json.get('resp', {})
                        if isinstance(resp_obj, dict):
                            err_msg = resp_obj.get('message') or "Maximum limit reached for this session."
                        else:
                            decrypted, _ = decrypt_response(resp_obj)
                            err_msg = decrypted.get('message') or "Maximum limit reached for this session."
                    except Exception:
                        err_msg = "Maximum limit reached for this session."
                    
                    bot.send_message(chat_id, f"<b>Stopped: {err_msg}</b>", parse_mode="HTML")
                    break
                
                if response.status == 200:
                    try:
                        res_json = json.loads(raw_text)
                        if 'resp' in res_json:
                            decrypted, success = decrypt_response(res_json['resp'])
                            if success:
                                reward_type = decrypted.get('rewardType', 'Unknown')
                                is_winner = decrypted.get('isWinner', False) or reward_type != 'BETTER_LUCK_NEXT_TIME'
                                
                                if is_winner:
                                    async with lock:
                                        session_data['won_rewards'] += 1
                                        current_wins = session_data['won_rewards']
                                        
                                    win_msg = (
                                        f"<b>Winner at Spin #{current_spin}!</b>\n\n"
                                        f"<b>Reward: {reward_type}</b>\n"
                                        f"<b>Wins Count: {current_wins}</b>\n\n"
                                        f"<b>Response:</b>\n<code>{json.dumps(decrypted, indent=2)}</code>"
                                    )
                                    bot.send_message(chat_id, win_msg, parse_mode="HTML")
                                    await update_progress_message(chat_id, force=True)
                    except Exception:
                        pass
        except Exception:
            pass
            
        await update_progress_message(chat_id)
        await asyncio.sleep(0.05)

async def run_async_spin_loop(chat_id):
    session_data = user_sessions.get(chat_id)
    if not session_data:
        return
        
    progress_msg = bot.send_message(chat_id, "<b>Login successful!...</b>", parse_mode="HTML")
    session_data['progress_msg_id'] = progress_msg.message_id
    session_data['last_edit_time'] = 0
    
    session_data['total_spins'] = 0
    session_data['won_rewards'] = 0
    lock = asyncio.Lock()
    
    async with aiohttp.ClientSession() as client:
        tasks = [asyncio.create_task(spin_worker(chat_id, client, lock)) for _ in range(100)]
        await asyncio.gather(*tasks)
        
    await update_progress_message(chat_id, force=True)
    
    bot.send_message(
        chat_id, 
        f"<b>finished!</b>\n\n"
        f"<b>Total Spins: {session_data['total_spins']}</b>\n"
        f"<b>Wins Reached: {session_data['won_rewards']}</b>", 
        parse_mode="HTML"
    )

def start_spin_loop_in_background(chat_id):
    t = threading.Thread(target=lambda: asyncio.run(run_async_spin_loop(chat_id)))
    t.start()

@bot.message_handler(func=lambda message: True)
def handle_inputs(message):
    chat_id = message.chat.id
    text = message.text.strip()
    
    session_data = user_sessions.get(chat_id)
    if not session_data:
        bot.reply_to(message, "<b>Session expired or not started. Please send /start to begin.</b>", parse_mode="HTML")
        return
        
    if session_data['state'] == "AWAITING_MOBILE":
        if not text.isdigit() or len(text) != 10:
            bot.reply_to(message, "<b>Invalid Number! Enter Number:</b>", parse_mode="HTML")
            return
            
        session_data['mobile'] = text
        
        collect_url = "https://discoverworldblends.in/api/collect"
        master_key = str(random.randint(100000000, 999999999))
        
        try:
            res = session_data['session'].post(
                collect_url, 
                json={"masterKey": master_key}, 
                headers={"content-type": "application/json", "accept": "application/json"}
            )
            
            if res.status_code == 200:
                res_json = res.json()
                if 'resp' in res_json:
                    decrypted, success = decrypt_response(res_json['resp'])
                    if success:
                        session_data['user_key'] = decrypted.get('userKey')
                        session_data['data_key'] = decrypted.get('dataKey')
                    else:
                        bot.send_message(chat_id, f"<b>Decryption of session metadata failed: {decrypted}</b>", parse_mode="HTML")
                        return
                else:
                    bot.send_message(chat_id, "<b>Invalid collect response from server.</b>", parse_mode="HTML")
                    return
            else:
                bot.send_message(chat_id, f"<b>Failed to initialize collect session: {res.status_code}</b>", parse_mode="HTML")
                return
        except Exception as e:
            bot.send_message(chat_id, f"<b>Collect request failed: {e}</b>", parse_mode="HTML")
            return
            
        pincode_url = f"https://discoverworldblends.in/api/users/pinCode/{session_data['user_key']}"
        payload = {
            "pincode": "110001",
            "userKey": session_data['user_key'],
            "t": int(time.time() * 1000)
        }
        res = make_request(session_data['session'], pincode_url, payload, session_data['user_key'], session_data['data_key'])
        if 'error' in res or res.get('statusCode') == 400:
            bot.send_message(chat_id, "<b>Pincode validation failed at server.</b>", parse_mode="HTML")
            return
            
        state_val = res.get('state')
        city_val = res.get('city')
            
        first_names = ["Aarav", "Vihaan", "Vivaan", "Ananya", "Diya", "Priya", "Rahul", "Amit", "Sanjay", "Rajesh", "Vikram", "Rohan", "Neha", "Sneha", "Karan", "Pooja", "Deepak", "Ravi", "Dev"]
        last_names = ["Sharma", "Verma", "Kumar", "Singh", "Gupta", "Joshi", "Mehra", "Patel", "Reddy", "Nair", "Das", "Roy", "Banerjee", "Mishra", "Choudhary"]
        session_data['name'] = f"{random.choice(first_names)} {random.choice(last_names)}"
        
        register_url = f"https://discoverworldblends.in/api/users/register/{session_data['user_key']}"
        payload = {
            "name": session_data['name'],
            "mobile": session_data['mobile'],
            "state": state_val,
            "city": city_val,
            "pincode": "110001",
            "agreeToTnc": True,
            "confirmAge": True,
            "userKey": session_data['user_key'],
            "t": int(time.time() * 1000)
        }
        res = make_request(session_data['session'], register_url, payload, session_data['user_key'], session_data['data_key'])
        if 'error' in res or res.get('statusCode') == 400:
            err_msg = res.get('message') or "Registration failed at server."
            bot.send_message(chat_id, f"<b>{err_msg}</b>", parse_mode="HTML")
            return
            
        session_data['state'] = "AWAITING_OTP"
        success_msg = "<b>Enter OTP:</b>"
        bot.send_message(chat_id, success_msg, parse_mode="HTML")
        
    elif session_data['state'] == "AWAITING_OTP":
        verify_url = f"https://discoverworldblends.in/api/users/verifyOTP/{session_data['user_key']}"
        payload = {
            "otp": text,
            "userKey": session_data['user_key'],
            "t": int(time.time() * 1000)
        }
        res = make_request(session_data['session'], verify_url, payload, session_data['user_key'], session_data['data_key'])
        if 'error' in res or res.get('statusCode') == 400 or res.get('statusCode') == 401:
            bot.send_message(chat_id, "<b>Invalid OTP! Enter OTP:</b>", parse_mode="HTML")
            return
            
        access_token = res.get('accessToken') or res.get('token')
        if not access_token:
            for k, v in res.items():
                if 'token' in k.lower() and isinstance(v, str):
                    access_token = v
                    break
                    
        if access_token:
            session_data['access_token'] = access_token
            session_data['state'] = "AUTHENTICATED"
            
            start_spin_loop_in_background(chat_id)
        else:
            bot.send_message(chat_id, "<b>Failed to extract access token from OTP response. Please send /start to try again.</b>", parse_mode="HTML")

if __name__ == "__main__":
    print("[+] Bot is running...")
    try:
        bot.infinity_polling()
    except Exception as e:
        pass
