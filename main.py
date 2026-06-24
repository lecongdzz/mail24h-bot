import os
import time
import random
import string
import threading
import json
import html
import asyncio
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
import requests

from pp import TempMailNinjaProClient

# ==========================================
# CẤU HÌNH MÔI TRƯỜNG & KHỞI TẠO BOT
# ==========================================
API_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8905972506:AAFklMbUqeRb-cM4iCwB_t30xiCIpAG2VK4")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "https://mail24h-bot.onrender.com")
WEBHOOK_URL = f"{WEBHOOK_HOST}/{API_TOKEN}/"
PORT = int(os.environ.get("PORT", 5000))

bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)

# ==========================================
# CƠ SỞ DỮ LIỆU GIẢ LẬP TRONG BỘ NHỚ
# ==========================================
MAIN_ADMIN = 8526421796
ADMINS = {MAIN_ADMIN: MAIN_ADMIN}

DB_USERS = {}
DB_BAN_LIST = {}

DB_CONFIG = {
    "logo": "https://images.unsplash.com/photo-1557200134-90327ee9fafa?w=800",
    "qr_bank": "https://api.vietqr.io/image/970422-190365899999-YL66FmK.jpg",
    "bank_info": "STK: 123456789\nNgân Hàng: MB Bank\nChủ Tài Khoản: NGUYEN VAN A",
    "price": 1000,
    "welcome_text": "🏢 <b>HỆ THỐNG MAIL 24H</b> 🏢\n\n📌 <b>CHỨC NĂNG CHÍNH</b>\n💰 Kiểm tra số dư\n📜 Xem lịch sử giao dịch\n📊 Theo dõi thu nhập\n👥 Quản lý dịch vụ\n🔔 Thông báo mới"
}

DB_STATS = {
    "deposits": [],
    "users": [],
    "spent": []
}

db_lock = threading.RLock()
DB_FILE = "database.json"

def load_data():
    global DB_USERS, DB_BAN_LIST, DB_CONFIG, DB_STATS
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                # Convert string keys back to int for DB_USERS and DB_BAN_LIST
                DB_USERS = {int(k): v for k, v in data.get("users", {}).items()}
                DB_BAN_LIST = {int(k): v for k, v in data.get("bans", {}).items()}
                
                # Cập nhật config (giữ nguyên cái mặc định nếu json thiếu)
                saved_config = data.get("config", {})
                for k, v in saved_config.items():
                    DB_CONFIG[k] = v
                
                DB_STATS = data.get("stats", {"deposits": [], "users": [], "spent": []})
        except Exception as e:
            print(f"Lỗi load DB: {e}")

def save_data():
    with db_lock:
        try:
            data = {
                "users": DB_USERS,
                "bans": DB_BAN_LIST,
                "config": DB_CONFIG,
                "stats": DB_STATS
            }
            with open(DB_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"Lỗi save DB: {e}")

# Gọi load data khi khởi chạy script
load_data()

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
UI_DIVIDER = "══════════════════════"
UI_FOOTER = (
    "<b>mail 24h Powered By DK Group - tangtuongtacsieure.com</b>\n"
    "© Bản quyền:\n"
    "👑 Admin: @tangtuongtacsieureadmin\n"
    "🛠 Support: @Lecongdzzz"
)

# ==========================================
# GIAO TIẾP API ẨN DANH TRÌNH DUYỆT (CHỐNG BOT)
# ==========================================
req_session = requests.Session()
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Linux; Android 13; Xiaomi Redmi Pad 2 Pro) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi-VN,vi;q=0.9,en-US;q=0.8",
    "Referer": "https://tempmail.ninja/",
    "Origin": "https://tempmail.ninja",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin"
}

# ==========================================
# KHỞI CHẠY LUỒNG TEMPMAIL NINJA NGẦM
# ==========================================
mail_client = TempMailNinjaProClient()
mail_loop = asyncio.new_event_loop()
mail_creation_lock = threading.Lock()

def start_mail_thread():
    asyncio.set_event_loop(mail_loop)
    # Khởi động kết nối Websocket với chế độ auto_mode=True (không chặn màn hình)
    mail_loop.run_until_complete(mail_client.start(auto_mode=True))

threading.Thread(target=start_mail_thread, daemon=True).start()

# ==========================================
# HÀM TIỆN ÍCH HỆ THỐNG
# ==========================================
def check_ban(user_id):
    if user_id in DB_BAN_LIST:
        ban_info = DB_BAN_LIST[user_id]
        if ban_info["unban_date"] == "0":
            return True, ban_info["ban_date"], ban_info["reason"], "Vĩnh viễn"
        
        unban_dt = datetime.strptime(ban_info["unban_date"], DATE_FORMAT)
        if datetime.now() > unban_dt:
            del DB_BAN_LIST[user_id]
            return False, "", "", ""
        return True, ban_info["ban_date"], ban_info["reason"], ban_info["unban_date"]
    return False, "", "", ""

def init_user(user_id, username):
    uname = html.escape(username) if username else f"User_{user_id}"
    with db_lock:
        if user_id not in DB_USERS:
            now_str = datetime.now().strftime(DATE_FORMAT)
            DB_USERS[user_id] = {
                "username": uname,
                "balance": 0,
                "total_deposit": 0,
                "current_mail": {},
                "history_mails": [],
                "strikes": 0
            }
            DB_STATS["users"].append({"uid": user_id, "username": uname, "time": now_str})
            save_data() # Lưu ngay khi có khách mới
        else:
            if DB_USERS[user_id]["username"] != uname:
                DB_USERS[user_id]["username"] = uname
                save_data()

def gen_history_markup(u_data):
    markup = InlineKeyboardMarkup(row_width=1)
    active_mails = []
    for item in reversed(u_data['history_mails']):
        rent_time = datetime.strptime(item['time'], DATE_FORMAT)
        if (datetime.now() - rent_time).total_seconds() < 86400:
            active_mails.append(item)
            if len(active_mails) >= 10: break
            
    if not active_mails: return None
    
    for item in active_mails:
        markup.add(InlineKeyboardButton(f"{item['email']}", callback_data=f"usr_histdetail_{item['order_id']}"))
    return markup

# ==========================================
# GIAO DIỆN BÀN PHÍM CỐ ĐỊNH (REPLY KEYBOARD)
# ==========================================
def get_user_reply_keyboard(user_id):
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("💰 Số dư"), KeyboardButton("📜 Lịch sử"))
    markup.add(KeyboardButton("👤 Thông tin"), KeyboardButton("📞 Hỗ trợ"))
    markup.add(KeyboardButton("📧 Thuê Mail"), KeyboardButton("💳 Nạp Tiền"))
    if user_id in ADMINS:
        markup.add(KeyboardButton("⚙️ MENU ADMIN"))
    return markup

def get_admin_main_reply_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("➕ Thêm Admin"), KeyboardButton("➖ Xóa Admin"))
    markup.add(KeyboardButton("📋 DS Admin"), KeyboardButton("🖼️ Đổi Logo"))
    markup.add(KeyboardButton("🏦 Cấu Hình Bank"), KeyboardButton("📝 Đổi Tiêu Đề"))
    markup.add(KeyboardButton("📊 Siêu Thống Kê"), KeyboardButton("📢 Gửi Thông Báo"))
    markup.add(KeyboardButton("🔍 Quản Lý User"), KeyboardButton("⬅️ Về Menu Khách"))
    return markup

def get_admin_user_reply_keyboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(KeyboardButton("💵 Cộng Tiền"), KeyboardButton("📉 Trừ Tiền"))
    markup.add(KeyboardButton("🚫 Phạt / Ban"), KeyboardButton("🔓 Mở Khóa"))
    markup.add(KeyboardButton("📜 Danh Sách Ban"), KeyboardButton("🔙 Trở Lại Admin"))
    return markup

# ==========================================
# XỬ LÝ LỆNH /START
# ==========================================
@bot.message_handler(commands=['start'])
def command_start(message):
    try:
        user_id = message.from_user.id
        uname = html.escape(message.from_user.username) if message.from_user.username else f"User_{user_id}"
        
        is_banned, b_date, reason, u_date = check_ban(user_id)
        if is_banned:
            text = (f"🚫 <b>TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA</b>\n{UI_DIVIDER}\n👤 Username: @{uname}\n🛑 Lý do: {html.escape(reason)}\n⏳ Hạn: {u_date}\n\n✉️ Liên hệ:\n👑 Admin: @tangtuongtacsieureadmin\n🛠 Support: @Lecongdzzz\n{UI_DIVIDER}\n{UI_FOOTER}")
            bot.send_message(message.chat.id, text, parse_mode="HTML")
            return
            
        init_user(user_id, uname)
        
        text = (
            f"👋 Xin chào @{uname}!\n"
            f"{UI_DIVIDER}\n"
            f"{DB_CONFIG['welcome_text']}\n"
            f"{UI_DIVIDER}\n"
            f"👇 <b>Chọn chức năng ở bàn phím bên dưới</b>\n\n"
            f"{UI_FOOTER}"
        )
        try: bot.send_photo(message.chat.id, photo=DB_CONFIG["logo"], caption=text, reply_markup=get_user_reply_keyboard(user_id), parse_mode="HTML")
        except: bot.send_message(message.chat.id, text=text, reply_markup=get_user_reply_keyboard(user_id), parse_mode="HTML")
            
    except Exception as e:
        print(f"Error in start: {e}")

# ==========================================
# XỬ LÝ TIN NHẮN TỪ BÀN PHÍM CHÍNH (USER)
# ==========================================
@bot.message_handler(func=lambda message: message.text in ["💰 Số dư", "📜 Lịch sử", "👤 Thông tin", "📞 Hỗ trợ", "📧 Thuê Mail", "💳 Nạp Tiền", "⬅️ Về Menu Khách"])
def handle_user_menu(message):
    try:
        user_id = message.from_user.id
        is_banned, _, _, _ = check_ban(user_id)
        if is_banned: return
            
        uname = message.from_user.username if message.from_user.username else f"User_{user_id}"
        init_user(user_id, uname)
        u_data = DB_USERS[user_id]

        if message.text == "⬅️ Về Menu Khách":
            bot.send_message(message.chat.id, "✅ Đã chuyển về giao diện người dùng thường.", reply_markup=get_user_reply_keyboard(user_id))

        elif message.text in ["💰 Số dư", "👤 Thông tin"]:
            text = (
                f"👤 <b>THÔNG TIN TÀI KHOẢN</b>\n"
                f"{UI_DIVIDER}\n"
                f"🆔 ID Telegram: <code>{user_id}</code>\n"
                f"👤 Tên hiển thị: <code>@{u_data['username']}</code>\n"
                f"💰 Số dư ví: <code>{u_data['balance']:,} VND</code>\n"
                f"💵 Tổng tiền nạp: <code>{u_data['total_deposit']:,} VND</code>\n"
                f"📧 Số mail đã thuê: <code>{len(u_data['history_mails'])}</code>\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.send_message(message.chat.id, text, reply_markup=get_user_reply_keyboard(user_id), parse_mode="HTML")

        elif message.text == "📜 Lịch sử":
            markup = gen_history_markup(u_data)
            if not markup:
                bot.send_message(message.chat.id, "⚠️ Bạn chưa có email nào khả dụng (trong 24h).", parse_mode="HTML")
            else:
                bot.send_message(message.chat.id, "🗂 <b>! Bạn có các email sau !</b> 🗂", reply_markup=markup, parse_mode="HTML")

        elif message.text == "📞 Hỗ trợ":
            text = f"📞 <b>THÔNG TIN HỖ TRỢ</b>\n{UI_DIVIDER}\n✉️ Mọi vấn đề lỗi vui lòng liên hệ Admin.\n{UI_DIVIDER}\n{UI_FOOTER}"
            bot.send_message(message.chat.id, text, parse_mode="HTML")

        elif message.text == "📧 Thuê Mail":
            price = DB_CONFIG["price"]
            with db_lock:
                if u_data['balance'] < price:
                    bot.send_message(message.chat.id, f"❌ Số dư không đủ <code>{price:,} VND</code>. Vui lòng nạp thêm!", parse_mode="HTML")
                    return
            
            msg_status = bot.send_message(message.chat.id, "⏳ <b>Đang vượt tường lửa Cloudflare tạo Email. Vui lòng không thao tác gì thêm, đợi khoảng 15s...</b>", parse_mode="HTML")
            
            with mail_creation_lock:
                try:
                    new_tk = asyncio.run_coroutine_threadsafe(mail_client.create_new_email_token(), mail_loop).result()
                    if not new_tk:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg_status.message_id, text="❌ Lỗi: Không thể vượt Captcha hệ thống mạng. Vui lòng thử lại sau.", parse_mode="HTML")
                        return
                    
                    mail_client.save_local_token(new_tk)
                    asyncio.run_coroutine_threadsafe(mail_client.action_initial_handshake(), mail_loop).result()
                    
                    # Cập nhật danh sách
                    asyncio.run_coroutine_threadsafe(mail_client.action_fetch_emails_list(), mail_loop).result()
                    
                    new_email = mail_client.active_email
                    if not new_email:
                        bot.edit_message_text(chat_id=message.chat.id, message_id=msg_status.message_id, text="❌ Lỗi: Hệ thống không trả về email nào.", parse_mode="HTML")
                        return
                        
                    order_id = f"ORD{random.randint(1000000, 9999999)}"
                    
                    with db_lock:
                        if u_data['balance'] < price:
                            bot.edit_message_text(chat_id=message.chat.id, message_id=msg_status.message_id, text="❌ Giao dịch thất bại do số dư thay đổi bất thường.", parse_mode="HTML")
                            return
                            
                        u_data['balance'] -= price
                        rent_time = datetime.now().strftime(DATE_FORMAT)
                        DB_STATS["spent"].append({"uid": user_id, "username": u_data['username'], "amount": price, "time": rent_time})
                        
                        mail_record = {"email": new_email, "order_id": order_id, "time": rent_time}
                        u_data['history_mails'].append(mail_record)
                        save_data()
                        
                    text = (
                        f"✅ <b>! Email của bạn đã sẵn sàng để nhận tin nhắn:</b>\n"
                        f"===========================\n"
                        f"¦ <code>{new_email}</code> ¦\n"
                        f"===========================\n"
                        f"Mã Đơn: <code>{order_id}</code>\n"
                        f"Giá thuê: {price:,} VND\n"
                        f"📬 ! Bây giờ bạn có thể nhận tin nhắn từ tất cả các trang web"
                    )
                    markup = InlineKeyboardMarkup(row_width=2)
                    markup.add(
                        InlineKeyboardButton("📩 Lấy tin nhắn", callback_data=f"usr_getotp_{order_id}"),
                        InlineKeyboardButton("🗑 Xóa email", callback_data=f"usr_delemail_{order_id}")
                    )
                    markup.add(InlineKeyboardButton("• Quay lại •", callback_data="usr_histback"))
                    bot.delete_message(chat_id=message.chat.id, message_id=msg_status.message_id)
                    bot.send_message(message.chat.id, text, reply_markup=markup, parse_mode="HTML")
                except Exception as e:
                    bot.edit_message_text(chat_id=message.chat.id, message_id=msg_status.message_id, text=f"❌ Lỗi hệ thống API tạo mail: {e}", parse_mode="HTML")

        elif message.text == "💳 Nạp Tiền":
            memo_str = f"MAIL24H_{user_id}_{''.join(random.choices(string.ascii_uppercase, k=4))}"
            text = (
                f"🏦 <b>CỔNG NẠP TIỀN TỰ ĐỘNG</b>\n"
                f"{UI_DIVIDER}\n"
                f"{DB_CONFIG['bank_info']}\n"
                f"📝 Nội dung CK: <code>{memo_str}</code>\n\n"
                f"⚠️ <b>CẢNH BÁO:</b> Tuyệt đối không gửi biên lai giả.\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📸 Gửi Bill Xác Nhận", callback_data=f"usr_sendbill_{memo_str}"))
            try: bot.send_photo(message.chat.id, photo=DB_CONFIG["qr_bank"], caption=text, reply_markup=markup, parse_mode="HTML")
            except: bot.send_message(message.chat.id, text=text, reply_markup=markup, parse_mode="HTML")

    except Exception as e:
        print(f"Error handling user menu: {e}")

# ==========================================
# XỬ LÝ INLINE CỦA USER (NHẬN OTP, XÓA EMAIL, GỬI BILL)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('usr_'))
def handle_user_inline(call):
    try:
        user_id = call.from_user.id
        u_data = DB_USERS.get(user_id)
        if not u_data: return

        if call.data == "usr_histback":
            markup = gen_history_markup(u_data)
            if markup:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂 <b>! Bạn có các email sau !</b> 🗂", reply_markup=markup, parse_mode="HTML")
            else:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ Bạn chưa có email nào khả dụng (trong 24h).", parse_mode="HTML")

        elif call.data.startswith("usr_histdetail_"):
            order_id = call.data.split("_")[2]
            mail_item = next((item for item in u_data['history_mails'] if item['order_id'] == order_id), None)
            
            if mail_item:
                rent_time = datetime.strptime(mail_item['time'], DATE_FORMAT)
                if (datetime.now() - rent_time).total_seconds() >= 86400:
                    bot.answer_callback_query(call.id, "❌ Email này đã quá 24h và bị xóa khỏi máy chủ!", show_alert=True)
                    return
                
                text = f"• <b>Email đã chọn</b>\n• <code>{mail_item['email']}</code>"
                markup = InlineKeyboardMarkup(row_width=2)
                markup.add(
                    InlineKeyboardButton("• Lấy tin nhắn •", callback_data=f"usr_getotp_{order_id}"),
                    InlineKeyboardButton("• Xóa email •", callback_data=f"usr_delemail_{order_id}")
                )
                markup.add(InlineKeyboardButton("• Quay lại •", callback_data="usr_histback"))
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="HTML")

        elif call.data.startswith("usr_delemail_"):
            parts = call.data.split("_")
            if len(parts) < 3: return
            order_id = parts[2]
            with db_lock:
                u_data['history_mails'] = [m for m in u_data['history_mails'] if m['order_id'] != order_id]
                save_data()
            bot.answer_callback_query(call.id, "✅ Đã xóa email khỏi lịch sử!", show_alert=True)
            
            markup = gen_history_markup(u_data)
            if markup:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="🗂 <b>! Bạn có các email sau !</b> 🗂", reply_markup=markup, parse_mode="HTML")
            else:
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⚠️ Bạn chưa có email nào khả dụng (trong 24h).", parse_mode="HTML")

        elif call.data.startswith("usr_getotp_"):
            parts = call.data.split("_")
            if len(parts) < 3: return
            order_id = parts[2]
            price = DB_CONFIG["price"]
            
            with db_lock:
                mail_item = next((item for item in u_data['history_mails'] if item['order_id'] == order_id), None)
                if not mail_item:
                    bot.answer_callback_query(call.id, "❌ Không tìm thấy thông tin email này!", show_alert=True)
                    return
                    
                rent_time = datetime.strptime(mail_item['time'], DATE_FORMAT)
                if (datetime.now() - rent_time).total_seconds() >= 86400:
                    bot.answer_callback_query(call.id, "❌ Email này đã quá 24h và bị xóa!", show_alert=True)
                    return
                    
                if u_data['balance'] < price:
                    bot.answer_callback_query(call.id, f"❌ Số dư không đủ {price:,} VND để lấy mã!", show_alert=True)
                    return
                
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="⏳ ! Đang tải tin nhắn từ Server Ninja...", parse_mode="HTML")
                
                u_data['balance'] -= price
                now_str = datetime.now().strftime(DATE_FORMAT)
                DB_STATS["spent"].append({"uid": user_id, "username": u_data['username'], "amount": price, "time": now_str})
                save_data()
            
            try:
                # Đồng bộ Inbox
                asyncio.run_coroutine_threadsafe(mail_client.action_fetch_inbox(silent=True), mail_loop).result()
                
                found_msg = None
                target_email = mail_item['email']
                
                if mail_client.messages_list:
                    # Tìm message theo recipient, nếu không có thì lấy message đầu tiên làm mặc định (fallback)
                    found_msg = mail_client.messages_list[0] 
                    for msg in mail_client.messages_list:
                        recip = msg.get('recipient') or msg.get('to') or ""
                        if target_email in recip:
                            found_msg = msg
                            break
                            
                if not found_msg:
                    # Hoàn tiền
                    with db_lock:
                        u_data['balance'] += price
                        DB_STATS["spent"] = [s for s in DB_STATS["spent"] if not (s['time'] == now_str and s['amount'] == price)]
                        save_data()
                    bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text="❌ Chưa có tin nhắn nào được gửi tới. Đã hoàn tiền!", parse_mode="HTML")
                    return
                    
                # Lấy chi tiết nội dung
                msg_id = found_msg['id']
                detail_res = asyncio.run_coroutine_threadsafe(mail_client.emit("get_email_message", [msg_id]), mail_loop).result()
                
                full_text_msg = "Không có nội dung rõ ràng, hãy kiểm tra tiêu đề."
                subject = found_msg.get('subject', 'Không tiêu đề')
                sender = found_msg.get('sender', {}).get('text', 'Ẩn danh')
                
                if detail_res and 'emailMessage' in detail_res:
                    detail = detail_res['emailMessage'].get('data', {})
                    full_text_msg = detail.get('text') or detail.get('html') or full_text_msg
                    
                display_text = f"<b>Từ:</b> <code>{html.escape(sender)}</code>\n<b>Tiêu đề:</b> <code>{html.escape(subject)}</code>\n\n<b>Nội dung:</b>\n<pre>{html.escape(full_text_msg[:1000])}</pre>"
                
            except Exception as e:
                with db_lock:
                    u_data['balance'] += price
                    save_data()
                bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=f"❌ Lỗi mạng Ninja: {e}. Đã hoàn tiền!", parse_mode="HTML")
                return
            
            markup = InlineKeyboardMarkup(row_width=2)
            markup.add(
                InlineKeyboardButton("• Lấy tin nhắn •", callback_data=f"usr_getotp_{order_id}"),
                InlineKeyboardButton("• Xóa email •", callback_data=f"usr_delemail_{order_id}")
            )
            markup.add(InlineKeyboardButton("• Quay lại •", callback_data="usr_histback"))
            
            try: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=display_text, reply_markup=markup, parse_mode="HTML")
            except: pass

        elif call.data.startswith("usr_sendbill_"):
            memo_str = call.data.replace("usr_sendbill_", "")
            msg = bot.send_message(call.message.chat.id, f"📸 <b>YÊU CẦU NẠP TIỀN:</b>\nVui lòng GỬI ẢNH CHỤP giao dịch chuyển khoản cho nội dung: <code>{memo_str}</code>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_user_bill, memo_str)

    except Exception as e:
        print(f"Error handling inline user: {e}")

def process_user_bill(message, memo_str):
    try:
        user_id = message.from_user.id
        if not message.photo:
            bot.reply_to(message, "❌ Bạn chưa gửi kèm ảnh. Vui lòng thao tác lại.")
            return
            
        photo_id = message.photo[-1].file_id
        username = DB_USERS[user_id]["username"]
        
        text_admin = (
            f"🔔 <b>DUYỆT NẠP TIỀN</b>\n"
            f"{UI_DIVIDER}\n"
            f"👤 Khách: @{username}\n"
            f"🆔 UID: <code>{user_id}</code>\n"
            f"📝 Nội dung: <code>{memo_str}</code>\n"
            f"{UI_DIVIDER}\n"
            f"{UI_FOOTER}"
        )
        markup_admin = InlineKeyboardMarkup(row_width=2)
        markup_admin.add(
            InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"admbill_yes_{user_id}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"admbill_no_{user_id}")
        )
        
        for admin_id in ADMINS.keys():
            try: bot.send_photo(chat_id=admin_id, photo=photo_id, caption=text_admin, reply_markup=markup_admin, parse_mode="HTML")
            except: pass
                
        bot.reply_to(message, "✅ Đã gửi biên lai cho Admin! Vui lòng đợi xét duyệt.")
    except Exception as e:
        print(f"Error process user bill: {e}")

# ==========================================
# XỬ LÝ MENU ADMIN (REPLY KEYBOARD)
# ==========================================
@bot.message_handler(func=lambda message: message.text in ["⚙️ MENU ADMIN", "➕ Thêm Admin", "➖ Xóa Admin", "📋 DS Admin", "🖼️ Đổi Logo", "🏦 Cấu Hình Bank", "📝 Đổi Tiêu Đề", "📊 Siêu Thống Kê", "📢 Gửi Thông Báo", "🔍 Quản Lý User", "🔙 Trở Lại Admin"])
def handle_admin_main(message):
    try:
        admin_id = message.from_user.id
        if admin_id not in ADMINS:
            return

        if message.text in ["⚙️ MENU ADMIN", "🔙 Trở Lại Admin"]:
            text = (
                f"👑 <b>PANEL ĐIỀU HÀNH ADMIN</b>\n"
                f"{UI_DIVIDER}\n"
                f"👤 Quyền hạn: Admin ID <code>{admin_id}</code>\n"
                f"📌 Lựa chọn tác vụ ở bàn phím bên dưới:\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.send_message(message.chat.id, text, reply_markup=get_admin_main_reply_keyboard(), parse_mode="HTML")

        elif message.text == "➕ Thêm Admin":
            msg = bot.send_message(message.chat.id, "✍️ Nhập UID Telegram của Admin mới:")
            bot.register_next_step_handler(msg, process_admin_add, admin_id)
            
        elif message.text == "➖ Xóa Admin":
            msg = bot.send_message(message.chat.id, "🗑 Nhập UID Admin muốn xóa:")
            bot.register_next_step_handler(msg, process_admin_del, admin_id)

        elif message.text == "📋 DS Admin":
            text = f"📋 <b>DANH SÁCH QUẢN TRỊ VIÊN</b>\n{UI_DIVIDER}\n"
            for uid, added_by in ADMINS.items():
                role = "👑 Admin Chính" if uid == MAIN_ADMIN else f"Thêm bởi {added_by}"
                text += f"🔹 UID: <code>{uid}</code> - {role}\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            bot.send_message(message.chat.id, text, parse_mode="HTML")

        elif message.text == "🖼️ Đổi Logo":
            msg = bot.send_message(message.chat.id, "🖼 Vui lòng GỬI ẢNH TRỰC TIẾP hoặc nhập Link URL để đổi Logo:")
            bot.register_next_step_handler(msg, process_admin_logo)

        elif message.text == "🏦 Cấu Hình Bank":
            msg = bot.send_message(message.chat.id, "🏦 Hãy GỬI ẢNH QR MỚI kèm DÒNG CHÚ THÍCH (Caption) ghi thông tin Ngân hàng.\n\nVí dụ gửi ảnh có chú thích:\n<code>STK: 12345\nBank: MB\nChủ: ABC</code>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_admin_bank)
            
        elif message.text == "📝 Đổi Tiêu Đề":
            msg = bot.send_message(message.chat.id, "📝 Nhập nội dung Menu / Lời Chào mới muốn hiển thị khi khách ấn /start:")
            bot.register_next_step_handler(msg, process_admin_title)

        elif message.text == "📊 Siêu Thống Kê":
            bot.send_message(message.chat.id, "⏳ Hệ thống đang truy xuất dữ liệu...", parse_mode="HTML")
            now = datetime.now()
            start_day = now.replace(hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            start_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            start_month = now.replace(day=1, hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            
            d_dep, w_dep, m_dep = 0, 0, 0
            u_day, u_week, u_month = [], [], []
            list_all_deposits = ""
            
            for d in DB_STATS["deposits"]:
                amt, dt = d["amount"], d["time"]
                list_all_deposits += f"🔹 <code>{d['uid']}</code> | @{d['username']} | +<code>{amt:,}</code>\n"
                if dt >= start_day: d_dep += amt
                if dt >= start_week: w_dep += amt
                if dt >= start_month: m_dep += amt
                
            for u in DB_STATS["users"]:
                dt = u["time"]
                entry = f"<code>{u['uid']}</code> | @{u['username']}"
                if dt >= start_day: u_day.append(entry)
                if dt >= start_week: u_week.append(entry)
                if dt >= start_month: u_month.append(entry)
                
            text = (
                f"📊 <b>BÁO CÁO DOANH THU & USER</b>\n"
                f"{UI_DIVIDER}\n"
                f"💰 Doanh thu Nạp: Ngày <code>{d_dep:,}</code> | Tuần <code>{w_dep:,}</code> | Tháng <code>{m_dep:,}</code>\n"
                f"👥 Mem mới: Ngày <code>{len(u_day)}</code> | Tuần <code>{len(u_week)}</code> | Tháng <code>{len(u_month)}</code>\n"
                f"📈 Tổng Mem hệ thống: <code>{len(DB_USERS)}</code>\n\n"
                f"👇 <b>Danh sách Mem mới hôm nay:</b>\n"
                f"{chr(10).join(u_day) if u_day else 'Chưa có'}\n\n"
                f"👇 <b>Danh sách Nạp tiền hệ thống:</b>\n"
                f"{list_all_deposits if list_all_deposits else 'Chưa có'}\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            if len(text) > 4000: text = text[:4000] + "\n... (Dữ liệu quá dài)"
            bot.send_message(message.chat.id, text, parse_mode="HTML")

        elif message.text == "📢 Gửi Thông Báo":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🌍 Gửi Toàn Hệ Thống", callback_data="brd_all"),
                InlineKeyboardButton("👤 Gửi UID Riêng", callback_data="brd_uid")
            )
            bot.send_message(message.chat.id, "📢 Chọn đối tượng nhận thông báo:", reply_markup=markup)

        elif message.text == "🔍 Quản Lý User":
            text = f"🔍 <b>QUẢN LÝ KHÁCH HÀNG</b>\n{UI_DIVIDER}\n📌 Chọn công cụ ở bàn phím bên dưới:"
            bot.send_message(message.chat.id, text, reply_markup=get_admin_user_reply_keyboard(), parse_mode="HTML")

    except Exception as e:
        print(f"Error handling admin main: {e}")

@bot.message_handler(func=lambda message: message.text in ["💵 Cộng Tiền", "📉 Trừ Tiền", "🚫 Phạt / Ban", "🔓 Mở Khóa", "📜 Danh Sách Ban"])
def handle_admin_user_mng(message):
    try:
        if message.from_user.id not in ADMINS: return
        
        if message.text == "💵 Cộng Tiền":
            msg = bot.send_message(message.chat.id, "💵 Nhập CỘNG TIỀN theo mẫu:\n<code>UID|Số_Tiền</code>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_admin_balance, "add")
        elif message.text == "📉 Trừ Tiền":
            msg = bot.send_message(message.chat.id, "📉 Nhập TRỪ TIỀN theo mẫu:\n<code>UID|Số_Tiền</code>", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_admin_balance, "sub")
        elif message.text == "🚫 Phạt / Ban":
            msg = bot.send_message(message.chat.id, "🚫 Nhập khóa người dùng theo mẫu:\n<code>UID|Lý_Do</code>\n(Lần 1 khóa 3 ngày, Lần 2 Vĩnh Viễn)", parse_mode="HTML")
            bot.register_next_step_handler(msg, process_admin_ban)
        elif message.text == "🔓 Mở Khóa":
            msg = bot.send_message(message.chat.id, "🔓 Nhập UID khách hàng cần GỠ BAN / XÓA CẢNH CÁO:")
            bot.register_next_step_handler(msg, process_admin_unban)
        elif message.text == "📜 Danh Sách Ban":
            text = f"📜 <b>DANH SÁCH ĐEN KHÁCH HÀNG</b>\n{UI_DIVIDER}\n"
            if not DB_BAN_LIST:
                text += "👉 Không có ai đang bị cấm.\n"
            else:
                for uid, info in DB_BAN_LIST.items():
                    text += f"🔹 UID: <code>{uid}</code>\n      Lý do: {info['reason']}\n      Hạn: {info['unban_date'] if info['unban_date'] != '0' else 'Vĩnh viễn'}\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            bot.send_message(message.chat.id, text, parse_mode="HTML")
    except Exception as e:
        print(f"Error handling admin user mng: {e}")

# ==========================================
# CÁC HÀM XỬ LÝ NEXT STEP CỦA ADMIN
# ==========================================
def process_admin_add(message, admin_id):
    try:
        new_uid = int(message.text.strip())
        if new_uid not in ADMINS:
            ADMINS[new_uid] = admin_id
            bot.reply_to(message, f"✅ Đã thêm Admin thành công: <code>{new_uid}</code>", parse_mode="HTML")
        else:
            bot.reply_to(message, "⚠️ UID này đã là Admin!")
    except: bot.reply_to(message, "❌ Yêu cầu nhập UID dạng số tự nhiên.")

def process_admin_del(message, admin_id):
    try:
        target_uid = int(message.text.strip())
        if target_uid not in ADMINS:
            bot.reply_to(message, "⚠️ UID này không phải là Admin.")
            return
        if target_uid == MAIN_ADMIN:
            bot.reply_to(message, "❌ Không thể xóa Admin gốc của hệ thống.")
            return
        if admin_id == MAIN_ADMIN or ADMINS[target_uid] == admin_id:
            del ADMINS[target_uid]
            bot.reply_to(message, f"✅ Đã tước quyền Admin của UID <code>{target_uid}</code>.", parse_mode="HTML")
        else:
            bot.reply_to(message, "❌ Bạn không có quyền xóa Admin này do không phải người thêm họ.")
    except: bot.reply_to(message, "❌ Sai định dạng.")

def process_admin_logo(message):
    try:
        with db_lock:
            if message.photo:
                DB_CONFIG["logo"] = message.photo[-1].file_id
                bot.reply_to(message, "✅ Đã cập nhật Logo bằng Hình Ảnh trực tiếp!")
            elif message.text:
                DB_CONFIG["logo"] = message.text.strip()
                bot.reply_to(message, "✅ Đã cập nhật Logo bằng Link URL!")
            else:
                bot.reply_to(message, "❌ Vui lòng gửi ảnh hoặc link.")
                return
            save_data()
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_bank(message):
    try:
        with db_lock:
            if message.photo and message.caption:
                DB_CONFIG["qr_bank"] = message.photo[-1].file_id
                DB_CONFIG["bank_info"] = message.caption.strip()
                bot.reply_to(message, "✅ Đã cập nhật cấu hình Ngân Hàng & QR Code bằng Hình Ảnh!")
            elif message.text and "|" in message.text:
                parts = message.text.split("|")
                DB_CONFIG["qr_bank"] = parts[0].strip()
                DB_CONFIG["bank_info"] = parts[1].strip()
                bot.reply_to(message, "✅ Đã cập nhật cấu hình Ngân Hàng bằng Text!")
            else:
                bot.reply_to(message, "❌ Thất bại. Nhớ gửi hình ảnh bắt buộc phải KÈM CHỮ ở phần chú thích (caption).")
                return
            save_data()
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_title(message):
    try:
        with db_lock:
            DB_CONFIG["welcome_text"] = message.text.strip()
            save_data()
        bot.reply_to(message, "✅ Đã thay đổi Tiêu Đề / Lời chào thành công! Hãy ấn /start để kiểm tra.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi thay đổi tiêu đề: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('brd_'))
def handle_broadcast_inline(call):
    if call.from_user.id not in ADMINS: return
    mode = call.data.split("_")[1]
    
    if mode == "all":
        msg = bot.send_message(call.message.chat.id, "📢 <b>Vui lòng gửi nội dung thông báo TỚI TOÀN BỘ USER:</b>\n(Hệ thống tự động nhận diện: Text, Ảnh kèm Caption, hoặc Video)", parse_mode="HTML")
        bot.register_next_step_handler(msg, execute_broadcast, None)
    else:
        msg = bot.send_message(call.message.chat.id, "👤 Nhập UID của người muốn gửi thông báo tới:")
        bot.register_next_step_handler(msg, process_brd_uid)

def process_brd_uid(message):
    try:
        target_uid = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"✍️ <b>Vui lòng gửi nội dung thông báo tới UID</b> <code>{target_uid}</code>:\n(Hỗ trợ: Text, Ảnh kèm Caption, Video)", parse_mode="HTML")
        bot.register_next_step_handler(msg, execute_broadcast, target_uid)
    except: 
        bot.reply_to(message, "❌ UID sai định dạng. Vui lòng thử lại.")

def execute_broadcast(message, target_uid):
    targets = [target_uid] if target_uid else list(DB_USERS.keys())
    success = 0
    for uid in targets:
        try:
            if message.photo: 
                bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption, parse_mode="HTML")
            elif message.video: 
                bot.send_video(uid, message.video.file_id, caption=message.caption, parse_mode="HTML")
            elif message.text:
                bot.send_message(uid, message.text, parse_mode="HTML")
            success += 1
        except: pass
            
    bot.reply_to(message, f"📢 Đã gửi thông báo thành công tới <code>{success}</code> tài khoản trong hệ thống.", parse_mode="HTML")

def process_admin_balance(message, action):
    try:
        parts = message.text.split("|")
        if len(parts) < 2:
            bot.reply_to(message, "❌ Định dạng phải là: <code>UID|Số_Tiền</code>", parse_mode="HTML")
            return
            
        target_uid = int(parts[0].strip())
        amount = int(parts[1].strip())
        
        if amount <= 0:
            bot.reply_to(message, "❌ Số tiền phải lớn hơn 0.")
            return
            
        with db_lock:
            if target_uid not in DB_USERS:
                bot.reply_to(message, "❌ User chưa khởi tạo.")
                return
                
            if action == "add":
                DB_USERS[target_uid]["balance"] += amount
                DB_USERS[target_uid]["total_deposit"] += amount
                save_data()
                bot.reply_to(message, f"✅ Đã cộng <code>+{amount:,} VND</code> cho <code>{target_uid}</code>.", parse_mode="HTML")
                try: bot.send_message(target_uid, f"🔔 <b>THÔNG BÁO:</b> Tài khoản của bạn được cộng <code>+{amount:,} VND</code>.", parse_mode="HTML")
                except: pass
            elif action == "sub":
                DB_USERS[target_uid]["balance"] = max(0, DB_USERS[target_uid]["balance"] - amount)
                save_data()
                bot.reply_to(message, f"✅ Đã trừ <code>-{amount:,} VND</code> của <code>{target_uid}</code>.", parse_mode="HTML")
                try: bot.send_message(target_uid, f"⚠️ <b>CẢNH BÁO:</b> Tài khoản của bạn bị khấu trừ <code>-{amount:,} VND</code>.", parse_mode="HTML")
                except: pass
    except: bot.reply_to(message, "❌ Định dạng phải là: <code>UID|Số_Tiền</code> (Ví dụ: 12345678|50000)", parse_mode="HTML")

def process_admin_ban(message):
    try:
        parts = message.text.split("|")
        if len(parts) < 2:
            bot.reply_to(message, "❌ Mẫu: <code>UID|Lý_Do</code>", parse_mode="HTML")
            return
        target_uid = int(parts[0].strip())
        reason = parts[1].strip()
        
        with db_lock:
            if target_uid not in DB_USERS:
                bot.reply_to(message, "❌ User chưa khởi tạo.")
                return
                
            strikes = DB_USERS[target_uid].get("strikes", 0) + 1
            DB_USERS[target_uid]["strikes"] = strikes
            ban_date = datetime.now().strftime(DATE_FORMAT)
            
            if strikes == 1:
                unban_date = (datetime.now() + timedelta(days=3)).strftime(DATE_FORMAT)
                DB_BAN_LIST[target_uid] = {"ban_date": ban_date, "reason": reason, "unban_date": unban_date}
                save_data()
                bot.reply_to(message, f"⚠️ Cảnh cáo lần 1 UID <code>{target_uid}</code>. Khóa 3 ngày.", parse_mode="HTML")
            else:
                unban_date = "0"
                DB_BAN_LIST[target_uid] = {"ban_date": ban_date, "reason": reason, "unban_date": unban_date}
                save_data()
                bot.reply_to(message, f"🛑 Vi phạm lần 2. Khóa VĨNH VIỄN UID <code>{target_uid}</code>.", parse_mode="HTML")
    except: bot.reply_to(message, "❌ Sai định dạng. Mẫu: <code>UID|Lý_Do</code>", parse_mode="HTML")

def process_admin_unban(message):
    try:
        target_uid = int(message.text.strip())
        with db_lock:
            if target_uid in DB_BAN_LIST:
                del DB_BAN_LIST[target_uid]
            if target_uid in DB_USERS:
                DB_USERS[target_uid]["strikes"] = 0
            save_data()
            
        bot.reply_to(message, f"✅ Đã gỡ Ban / Xóa thẻ phạt cho UID <code>{target_uid}</code>.", parse_mode="HTML")
        try: bot.send_message(target_uid, "🎉 <b>CHÚC MỪNG:</b> Tài khoản đã được gỡ cấm. Gõ /start để tiếp tục.", parse_mode="HTML")
        except: pass
    except: bot.reply_to(message, "❌ Lỗi định dạng UID.")

# DUYỆT BILL INLINE CỦA ADMIN
@bot.callback_query_handler(func=lambda call: call.data.startswith('admbill_'))
def handle_bill_approval(call):
    admin_id = call.from_user.id
    if admin_id not in ADMINS: return
    
    if call.data.startswith("admbill_yes_"):
        target_uid = int(call.data.replace("admbill_yes_", ""))
        msg = bot.send_message(call.message.chat.id, f"✅ NHẬP SỐ TIỀN CẦN CỘNG cho UID <code>{target_uid}</code>:", parse_mode="HTML")
        bot.register_next_step_handler(msg, process_bill_approve, target_uid, call.message.message_id, call.message.chat.id)

    elif call.data.startswith("admbill_no_"):
        target_uid = int(call.data.replace("admbill_no_", ""))
        try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=f"❌ ĐÃ TỪ CHỐI BỞI ADMIN: <code>{admin_id}</code>", parse_mode="HTML")
        except: pass
        try: bot.send_message(target_uid, "❌ <b>THÔNG BÁO TỪ CHỐI:</b>\nGiao dịch nạp tiền bị từ chối do biên lai không hợp lệ hoặc sai cú pháp.", parse_mode="HTML")
        except: pass

def process_bill_approve(message, target_uid, orig_msg_id, orig_chat_id):
    try:
        amount = int(message.text.strip())
        if amount <= 0:
            bot.reply_to(message, "❌ Số tiền nạp phải lớn hơn 0.")
            return
            
        with db_lock:
            if target_uid not in DB_USERS:
                bot.reply_to(message, "❌ Người dùng chưa khởi tạo.")
                return
                
            DB_USERS[target_uid]["balance"] += amount
            DB_USERS[target_uid]["total_deposit"] += amount
            
            now_str = datetime.now().strftime(DATE_FORMAT)
            uname = DB_USERS[target_uid]["username"]
            DB_STATS["deposits"].append({"uid": target_uid, "username": uname, "amount": amount, "time": now_str})
            save_data()
            
        bot.reply_to(message, f"✅ Đã cộng <code>+{amount:,} VND</code>.", parse_mode="HTML")
        try: bot.edit_message_caption(chat_id=orig_chat_id, message_id=orig_msg_id, caption=f"✅ ĐÃ DUYỆT CỘNG: <code>+{amount:,} VND</code>\nBởi Admin: <code>{message.from_user.id}</code>", parse_mode="HTML")
        except: pass
        
        try: bot.send_message(target_uid, f"🎉 <b>NẠP THÀNH CÔNG:</b> Tài khoản của bạn được cộng <code>+{amount:,} VND</code>.", parse_mode="HTML")
        except: pass
    except: bot.reply_to(message, "❌ Vui lòng nhập Số Tiền bằng ký tự số hợp lệ.")

# ==========================================
# KHỞI CHẠY KIẾN TRÚC WEBHOOK
# ==========================================
@app.route('/', methods=['GET', 'HEAD'])
def health_check():
    return "Hệ thống Bot đang vận hành!", 200

@app.route(f'/{API_TOKEN}/', methods=['POST'])
def receive_updates():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

if __name__ == '__main__':
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    app.run(host="0.0.0.0", port=PORT)
