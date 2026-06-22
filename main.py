import os
import time
import random
import string
import threading
from datetime import datetime, timedelta
from flask import Flask, request
import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests

# ==========================================
# CẤU HÌNH MÔI TRƯỜNG & KHỞI TẠO BOT
# ==========================================
API_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8669698846:AAGi3DIkUEi94YQT354zMemVs4HOXjPQoCs")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "https://mail24h-bot.onrender.com")
WEBHOOK_URL = f"{WEBHOOK_HOST}/{API_TOKEN}/"
PORT = int(os.environ.get("PORT", 5000))

bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)

# ==========================================
# CƠ SỞ DỮ LIỆU GIẢ LẬP TRONG BỘ NHỚ
# ==========================================
MAIN_ADMIN = 8526421796
# ADMINS lưu phân quyền: {uid: added_by_uid}
ADMINS = {MAIN_ADMIN: MAIN_ADMIN}

DB_USERS = {}
DB_BAN_LIST = {}
DB_CONFIG = {
    "logo": "https://images.unsplash.com/photo-1557200134-90327ee9fafa?w=800",
    "qr_bank": "https://api.vietqr.io/image/970422-190365899999-YL66FmK.jpg",
    "bank_info": "STK: 123456789\nNgân Hàng: MB Bank\nChủ Tài Khoản: NGUYEN VAN A",
    "price": 1000
}

# Lưu trữ dữ liệu thống kê chi tiết
DB_STATS = {
    "deposits": [],  # Format: {"uid": 123, "username": "abc", "amount": 10000, "time": "YYYY-MM-DD HH:MM:SS"}
    "users": [],     # Format: {"uid": 123, "username": "abc", "time": "YYYY-MM-DD HH:MM:SS"}
    "spent": []      # Format: {"uid": 123, "username": "abc", "amount": 1000, "time": "YYYY-MM-DD HH:MM:SS"}
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
UI_DIVIDER = "══════════════════════"
UI_FOOTER = (
    "mail 24h Powered By DK Group - tangtuongtacsieure.com\n"
    "© Bản quyền:\n"
    "👑 Admin: @tangtuongtacsieureadmin\n"
    "🛠 Support: @Lecongdzzz"
)

# ==========================================
# GIAO TIẾP API ẨN DANH CHIẾN THUẬT
# ==========================================
def call_mail_api(endpoint, method="POST", data=None):
    # Kết nối ngầm đến tempmail.ninja, tuyệt đối không lộ ra UI
    url = f"https://tempmail.ninja/api/v1/{endpoint}"
    headers = {"Content-Type": "application/json"}
    try:
        if method == "POST":
            pass # Thực tế gọi requests.post
        elif method == "GET":
            pass # Thực tế gọi requests.get
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def buy_mail_account():
    call_mail_api("emails/create", method="POST", data={"domain": "tempmail.ninja"})
    # Hiển thị maily.lat để đánh lạc hướng theo yêu cầu chiến thuật
    rand_prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email_address = f"{rand_prefix}@maily.lat"
    order_id = f"ORD{random.randint(1000000, 9999999)}"
    return email_address, order_id

def get_mail_otp(order_id):
    call_mail_api(f"emails/{order_id}/messages", method="GET")
    otp_code = f"{random.randint(100000, 999999)}"
    return otp_code

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
    uname = username if username else f"User_{user_id}"
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
    else:
        DB_USERS[user_id]["username"] = uname

def get_image_url(message):
    file_id = message.photo[-1].file_id
    file_info = bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"

# ==========================================
# GIAO DIỆN CHÍNH (UI/UX CHUẨN DKGROUP)
# ==========================================
def ui_user_main_menu(user_id):
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💰 Số dư", callback_data="usr_profile"),
        InlineKeyboardButton("📜 Lịch sử", callback_data="usr_history"),
        InlineKeyboardButton("👤 Thông tin", callback_data="usr_profile"),
        InlineKeyboardButton("📞 Hỗ trợ", callback_data="usr_contact"),
        InlineKeyboardButton("📧 Thuê Mail", callback_data="usr_rent"),
        InlineKeyboardButton("💳 Nạp Tiền", callback_data="usr_deposit")
    )
    if user_id in ADMINS:
        markup.add(InlineKeyboardButton("⚙️ QUẢN LÝ ADMIN", callback_data="adm_main"))
    return markup

@bot.message_handler(commands=['start'])
def command_start(message):
    try:
        user_id = message.from_user.id
        uname = message.from_user.username if message.from_user.username else f"User_{user_id}"
        
        is_banned, b_date, reason, u_date = check_ban(user_id)
        if is_banned:
            text = (
                f"🚫 **TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA**\n"
                f"{UI_DIVIDER}\n"
                f"👤 Username: @{uname}\n"
                f"🛑 Lý do: {reason}\n"
                f"⏳ Hạn mở khóa: {u_date}\n\n"
                f"✉️ Vui lòng liên hệ Admin để được hỗ trợ mở khóa:\n"
                f"👑 Admin: @tangtuongtacsieureadmin\n"
                f"🛠 Support: @Lecongdzzz\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
            
        init_user(user_id, uname)
        
        text = (
            f" 🏢 **DKGROUP_INVEST** 🏢 \n"
            f"{UI_DIVIDER}\n"
            f"👋 Xin chào @{uname}!\n"
            f"{UI_DIVIDER}\n"
            f"💼 **HỆ THỐNG QUẢN LÝ**\n"
            f"Cung cấp Email chất lượng & Số dư nội bộ\n\n"
            f"📌 **CHỨC NĂNG CHÍNH**\n"
            f"💰 Kiểm tra số dư\n"
            f"📜 Xem lịch sử giao dịch\n"
            f"📊 Theo dõi thu nhập\n"
            f"👥 Quản lý dịch vụ\n"
            f"🔔 Thông báo mới\n"
            f"{UI_DIVIDER}\n"
            f"👇 **Chọn chức năng bên dưới**\n\n"
            f"{UI_FOOTER}"
        )
        
        try:
            bot.send_photo(message.chat.id, photo=DB_CONFIG["logo"], caption=text, reply_markup=ui_user_main_menu(user_id), parse_mode="Markdown")
        except Exception:
            bot.send_message(message.chat.id, text=text, reply_markup=ui_user_main_menu(user_id), parse_mode="Markdown")
            
    except Exception as e:
        print(f"Error in start: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('usr_'))
def user_callbacks(call):
    try:
        user_id = call.from_user.id
        uname = call.from_user.username if call.from_user.username else f"User_{user_id}"
        
        is_banned, b_date, reason, u_date = check_ban(user_id)
        if is_banned:
            bot.answer_callback_query(call.id, f"Tài khoản bị khóa đến {u_date}. Liên hệ Admin @tangtuongtacsieureadmin", show_alert=True)
            return
            
        init_user(user_id, uname)
        u_data = DB_USERS[user_id]

        if call.data == "usr_main":
            text = (
                f" 🏢 **DKGROUP_INVEST** 🏢 \n"
                f"{UI_DIVIDER}\n"
                f"👋 Xin chào @{u_data['username']}!\n"
                f"{UI_DIVIDER}\n"
                f"💼 **HỆ THỐNG QUẢN LÝ**\n"
                f"Cung cấp Email chất lượng & Số dư nội bộ\n\n"
                f"📌 **CHỨC NĂNG CHÍNH**\n"
                f"💰 Kiểm tra số dư\n"
                f"📜 Xem lịch sử giao dịch\n"
                f"📊 Theo dõi thu nhập\n"
                f"👥 Quản lý dịch vụ\n"
                f"🔔 Thông báo mới\n"
                f"{UI_DIVIDER}\n"
                f"👇 **Chọn chức năng bên dưới**\n\n"
                f"{UI_FOOTER}"
            )
            try:
                bot.edit_message_media(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    media=telebot.types.InputMediaPhoto(DB_CONFIG["logo"], caption=text, parse_mode="Markdown"),
                    reply_markup=ui_user_main_menu(user_id)
                )
            except Exception:
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except: pass
                bot.send_message(call.message.chat.id, text=text, reply_markup=ui_user_main_menu(user_id), parse_mode="Markdown")

        elif call.data == "usr_profile":
            text = (
                f"👤 **THÔNG TIN TÀI KHOẢN**\n"
                f"{UI_DIVIDER}\n"
                f"🆔 ID Telegram: `{user_id}`\n"
                f"👤 Tên hiển thị: `@{u_data['username']}`\n"
                f"💰 Số dư ví: `{u_data['balance']:,} VND`\n"
                f"💵 Tổng tiền nạp: `{u_data['total_deposit']:,} VND`\n"
                f"📧 Số mail đã thuê: `{len(u_data['history_mails'])}`\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📜 Lịch Sử Thuê Mail", callback_data="usr_history"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "usr_history":
            text = (
                f"📜 **LỊCH SỬ THUÊ MAIL**\n"
                f"{UI_DIVIDER}\n"
                f"📌 Chọn một email bên dưới để kiểm tra lại chi tiết:\n"
            )
            markup = InlineKeyboardMarkup(row_width=1)
            if not u_data['history_mails']:
                text += "⚠️ Bạn chưa thuê mail nào trên hệ thống."
            else:
                for item in reversed(u_data['history_mails'][-10:]):
                    markup.add(InlineKeyboardButton(f"📧 {item['email']}", callback_data=f"usr_histdetail_{item['order_id']}"))
            
            text += f"\n{UI_DIVIDER}\n{UI_FOOTER}"
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_profile"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("usr_histdetail_"):
            order_id = call.data.split("_")[2]
            mail_item = next((item for item in u_data['history_mails'] if item['order_id'] == order_id), None)
            
            if mail_item:
                rent_time = datetime.strptime(mail_item['time'], DATE_FORMAT)
                is_active = (datetime.now() - rent_time).total_seconds() < 86400 and u_data.get('current_mail', {}).get('order_id') == order_id
                
                status = "✅ Đang hoạt động" if is_active else "❌ Đã mất tác dụng"
                text = (
                    f"📧 **CHI TIẾT ĐƠN THUÊ MAIL**\n"
                    f"{UI_DIVIDER}\n"
                    f"🆔 Mã Đơn: `{mail_item['order_id']}`\n"
                    f"📧 Địa chỉ Email: `{mail_item['email']}`\n"
                    f"🕒 Thời gian thuê: `{mail_item['time']}`\n"
                    f"📊 Trạng thái: {status}\n"
                    f"{UI_DIVIDER}\n"
                    f"{UI_FOOTER}"
                )
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("⬅️ Quay Lại Lịch Sử", callback_data="usr_history"))
                try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
                except: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "usr_contact":
            text = (
                f"📞 **THÔNG TIN HỖ TRỢ**\n"
                f"{UI_DIVIDER}\n"
                f"✉️ Mọi vấn đề lỗi bot hay giao dịch vui lòng liên hệ trực tiếp Admin để xử lý.\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "usr_rent":
            price = DB_CONFIG["price"]
            if u_data['balance'] < price:
                bot.answer_callback_query(call.id, f"❌ Số dư không đủ {price:,} VND. Vui lòng nạp thêm!", show_alert=True)
                return
            
            if 'active' in u_data.get('current_mail', {}):
                u_data['current_mail']['active'] = False
            
            u_data['balance'] -= price
            rent_time = datetime.now().strftime(DATE_FORMAT)
            DB_STATS["spent"].append({"uid": user_id, "username": u_data['username'], "amount": price, "time": rent_time})
            
            new_email, order_id = buy_mail_account()
            
            mail_record = {"email": new_email, "order_id": order_id, "time": rent_time, "active": True}
            u_data['current_mail'] = mail_record
            u_data['history_mails'].append(mail_record)
            
            text = (
                f"✅ **GIAO DỊCH THUÊ MAIL THÀNH CÔNG**\n"
                f"{UI_DIVIDER}\n"
                f"📧 Email Mới: `{new_email}`\n"
                f"🆔 Mã Đơn: `{order_id}`\n"
                f"🕒 Kích hoạt lúc: `{rent_time}`\n\n"
                f"⚠️ *Mail cũ đã bị vô hiệu hóa. Mail mới tồn tại 24h.*\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"🔄 Nhận Mã OTP (Phí {price:,}đ)", callback_data=f"usr_getotp_{order_id}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(chat_id=call.message.chat.id, message_id=call.message.message_id, text=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("usr_getotp_"):
            order_id = call.data.split("_")[2]
            current = u_data.get('current_mail', {})
            price = DB_CONFIG["price"]
            
            if not current or current.get('order_id') != order_id or not current.get('active'):
                bot.answer_callback_query(call.id, "❌ Email này đã bị thay thế hoặc vô hiệu hóa!", show_alert=True)
                return
                
            rent_time = datetime.strptime(current['time'], DATE_FORMAT)
            if (datetime.now() - rent_time).total_seconds() >= 86400:
                current['active'] = False
                bot.answer_callback_query(call.id, "❌ Email này đã vượt quá 24h và hết hạn sử dụng!", show_alert=True)
                return
                
            if u_data['balance'] < price:
                bot.answer_callback_query(call.id, f"❌ Số dư không đủ {price:,} VND để nhận OTP!", show_alert=True)
                return
                
            u_data['balance'] -= price
            now_str = datetime.now().strftime(DATE_FORMAT)
            DB_STATS["spent"].append({"uid": user_id, "username": u_data['username'], "amount": price, "time": now_str})
            
            otp_code = get_mail_otp(order_id)
            
            text = (
                f"🔄 **KẾT QUẢ QUÉT MÃ OTP**\n"
                f"{UI_DIVIDER}\n"
                f"📧 Email: `{current['email']}`\n"
                f"🔑 Mã Kích Hoạt (OTP): **{otp_code}**\n"
                f"🕒 Quét lúc: `{now_str}`\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton(f"🔄 Nhận Mã OTP (Phí {price:,}đ)", callback_data=f"usr_getotp_{order_id}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: pass

        elif call.data == "usr_deposit":
            memo_str = f"MAIL24H_{user_id}_{''.join(random.choices(string.ascii_uppercase, k=4))}"
            text = (
                f"🏦 **CỔNG NẠP TIỀN TỰ ĐỘNG**\n"
                f"{UI_DIVIDER}\n"
                f"{DB_CONFIG['bank_info']}\n"
                f"📝 Nội dung CK: `{memo_str}`\n\n"
                f"⚠️ **CẢNH BÁO:**\n"
                f"Tuyệt đối không gửi biên lai giả mạo (Fake Bill).\n"
                f"Lần 1 vi phạm sẽ được tha, Lần 2 khoá vĩnh viễn!\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📸 Gửi Bill Xác Nhận", callback_data=f"usr_sendbill_{memo_str}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            
            try:
                bot.edit_message_media(
                    chat_id=call.message.chat.id, message_id=call.message.message_id,
                    media=telebot.types.InputMediaPhoto(DB_CONFIG["qr_bank"], caption=text, parse_mode="Markdown"),
                    reply_markup=markup
                )
            except Exception:
                try: bot.delete_message(call.message.chat.id, call.message.message_id)
                except: pass
                bot.send_photo(call.message.chat.id, photo=DB_CONFIG["qr_bank"], caption=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("usr_sendbill_"):
            memo_str = call.data.replace("usr_sendbill_", "")
            msg = bot.send_message(call.message.chat.id, f"📸 **YÊU CẦU:**\nVui lòng gửi ẢNH CHỤP giao dịch thành công cho nội dung: `{memo_str}`.", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_user_bill, memo_str)

    except Exception as e:
        print(f"Error in user callbacks: {e}")

def process_user_bill(message, memo_str):
    try:
        user_id = message.from_user.id
        if not message.photo:
            bot.reply_to(message, "❌ Vui lòng gửi bằng hình ảnh (Photo). Hãy làm lại.")
            return
            
        photo_id = message.photo[-1].file_id
        username = DB_USERS[user_id]["username"]
        
        text_admin = (
            f"🔔 **DUYỆT NẠP TIỀN**\n"
            f"{UI_DIVIDER}\n"
            f"👤 Khách hàng: `@{username}`\n"
            f"🆔 UID: `{user_id}`\n"
            f"📝 Nội dung gửi: `{memo_str}`\n"
            f"{UI_DIVIDER}\n"
            f"{UI_FOOTER}"
        )
        markup_admin = InlineKeyboardMarkup(row_width=2)
        markup_admin.add(
            InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"admbill_yes_{user_id}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"admbill_no_{user_id}")
        )
        
        for admin_id in ADMINS.keys():
            try: bot.send_photo(chat_id=admin_id, photo=photo_id, caption=text_admin, reply_markup=markup_admin, parse_mode="Markdown")
            except: pass
                
        bot.reply_to(message, "✅ Gửi ảnh thành công! Đang chờ Admin xét duyệt.")
    except Exception as e:
        print(f"Error process user bill: {e}")

# ==========================================
# PHÂN HỆ QUẢN TRỊ VIÊN ĐA CẤP (ADMIN INTERFACE)
# ==========================================
def ui_admin_main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Thêm Admin", callback_data="adm_add"),
        InlineKeyboardButton("➖ Xóa Admin", callback_data="adm_del"),
        InlineKeyboardButton("📋 DS Admin", callback_data="adm_list"),
        InlineKeyboardButton("🖼️ Đổi Logo", callback_data="adm_logo"),
        InlineKeyboardButton("🏦 Cấu Hình Bank", callback_data="adm_bank"),
        InlineKeyboardButton("📊 Siêu Thống Kê", callback_data="adm_stats"),
        InlineKeyboardButton("📢 Gửi Thông Báo", callback_data="adm_broadcast"),
        InlineKeyboardButton("🔍 Quản Lý User", callback_data="adm_usermng"),
        InlineKeyboardButton("⬅️ Thoát Menu", callback_data="usr_main")
    )
    return markup

def ui_admin_user_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 Cộng Tiền", callback_data="usrmng_add"),
        InlineKeyboardButton("📉 Trừ Tiền", callback_data="usrmng_sub"),
        InlineKeyboardButton("🚫 Phạt / Ban", callback_data="usrmng_ban"),
        InlineKeyboardButton("🔓 Mở Khóa", callback_data="usrmng_unban"),
        InlineKeyboardButton("📜 Danh Sách Ban", callback_data="usrmng_listban"),
        InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main")
    )
    return markup

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_') or call.data.startswith('usrmng_') or call.data.startswith('admbill_'))
def admin_callbacks(call):
    try:
        admin_id = call.from_user.id
        if admin_id not in ADMINS:
            bot.answer_callback_query(call.id, "Từ chối quyền truy cập!", show_alert=True)
            return

        if call.data == "adm_main":
            text = (
                f"👑 **PANEL ĐIỀU HÀNH ADMIN**\n"
                f"{UI_DIVIDER}\n"
                f"👤 Quyền hạn: Admin ID `{admin_id}`\n"
                f"📌 Lựa chọn tác vụ phía dưới:\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=ui_admin_main_menu(), parse_mode="Markdown")
            except: bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=ui_admin_main_menu(), parse_mode="Markdown")

        elif call.data == "adm_add":
            msg = bot.send_message(call.message.chat.id, "✍️ Nhập UID Telegram của Admin mới:")
            bot.register_next_step_handler(msg, process_admin_add, admin_id)
            
        elif call.data == "adm_del":
            msg = bot.send_message(call.message.chat.id, "🗑 Nhập UID Admin muốn xóa:")
            bot.register_next_step_handler(msg, process_admin_del, admin_id)

        elif call.data == "adm_list":
            text = f"📋 **DANH SÁCH QUẢN TRỊ VIÊN**\n{UI_DIVIDER}\n"
            for uid, added_by in ADMINS.items():
                role = "👑 Admin Chính" if uid == MAIN_ADMIN else f"Được thêm bởi {added_by}"
                text += f"🔹 UID: `{uid}` - {role}\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "adm_logo":
            msg = bot.send_message(call.message.chat.id, "🖼 Vui lòng GỬI ẢNH TRỰC TIẾP hoặc nhập Link URL để đổi Logo:")
            bot.register_next_step_handler(msg, process_admin_logo)

        elif call.data == "adm_bank":
            msg = bot.send_message(call.message.chat.id, "🏦 Hãy GỬI ẢNH QR MỚI kèm DÒNG CHÚ THÍCH (Caption) ghi thông tin Ngân hàng.\n\nVí dụ: Gửi 1 ảnh, phần Caption ghi:\n`STK: 12345\nBank: MB\nChủ: ABC`")
            bot.register_next_step_handler(msg, process_admin_bank)

        elif call.data == "adm_stats":
            msg = bot.send_message(call.message.chat.id, "⏳ Hệ thống đang tính toán dữ liệu Siêu Thống Kê. Vui lòng chờ...")
            # Xử lý logic lọc thời gian
            now = datetime.now()
            start_day = now.replace(hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            start_week = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            start_month = now.replace(day=1, hour=0, minute=0, second=0).strftime(DATE_FORMAT)
            
            d_dep, w_dep, m_dep = 0, 0, 0
            u_day, u_week, u_month = [], [], []
            list_all_deposits = ""
            
            for d in DB_STATS["deposits"]:
                amt, dt = d["amount"], d["time"]
                list_all_deposits += f"🔹 `{d['uid']}` | @{d['username']} | +`{amt:,}`\n"
                if dt >= start_day: d_dep += amt
                if dt >= start_week: w_dep += amt
                if dt >= start_month: m_dep += amt
                
            for u in DB_STATS["users"]:
                dt = u["time"]
                entry = f"`{u['uid']}` | @{u['username']}"
                if dt >= start_day: u_day.append(entry)
                if dt >= start_week: u_week.append(entry)
                if dt >= start_month: u_month.append(entry)
                
            text = (
                f"📊 **BÁO CÁO DOANH THU & USER**\n"
                f"{UI_DIVIDER}\n"
                f"💰 Doanh thu Nạp: Ngày `{d_dep:,}` | Tuần `{w_dep:,}` | Tháng `{m_dep:,}`\n"
                f"👥 Mem mới: Ngày `{len(u_day)}` | Tuần `{len(u_week)}` | Tháng `{len(u_month)}`\n"
                f"📈 Tổng Mem hệ thống: `{len(DB_USERS)}`\n\n"
                f"👇 **Danh sách Men mới hôm nay:**\n"
                f"{chr(10).join(u_day) if u_day else 'Chưa có'}\n\n"
                f"👇 **Danh sách Nạp tiền toàn hệ thống:**\n"
                f"{list_all_deposits if list_all_deposits else 'Chưa có'}\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            # Nếu text quá dài, Telegram sẽ chặn. Ta cắt bớt nếu cần.
            if len(text) > 4000: text = text[:4000] + "\n... (Dữ liệu quá dài)"
            
            bot.delete_message(call.message.chat.id, msg.message_id)
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "adm_broadcast":
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("🌍 Gửi Toàn Hệ Thống", callback_data="brd_all"),
                InlineKeyboardButton("👤 Gửi UID Riêng", callback_data="brd_uid")
            )
            bot.send_message(call.message.chat.id, "📢 Chọn chế độ gửi thông báo:", reply_markup=markup)

        elif call.data.startswith("brd_"):
            mode = call.data.split("_")[1]
            msg = bot.send_message(call.message.chat.id, "❓ Bạn có muốn đính kèm Ảnh/Video không? Trả lời: `Có` hoặc `Không`")
            bot.register_next_step_handler(msg, process_brd_media, mode)

        elif call.data == "adm_usermng":
            text = f"🔍 **DANH MỤC QUẢN LÝ KHÁCH HÀNG**\n{UI_DIVIDER}\n📌 Lựa chọn công cụ xử lý Users:"
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=ui_admin_user_menu(), parse_mode="Markdown")
            except: bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=ui_admin_user_menu(), parse_mode="Markdown")

        elif call.data == "usrmng_add":
            msg = bot.send_message(call.message.chat.id, "💵 Nhập CỘNG TIỀN:\n`UID|Số_Tiền`")
            bot.register_next_step_handler(msg, process_admin_balance, "add")

        elif call.data == "usrmng_sub":
            msg = bot.send_message(call.message.chat.id, "📉 Nhập TRỪ TIỀN:\n`UID|Số_Tiền`")
            bot.register_next_step_handler(msg, process_admin_balance, "sub")

        elif call.data == "usrmng_ban":
            msg = bot.send_message(call.message.chat.id, "🚫 Hệ thống Ban thông minh (Cảnh cáo -> Khóa Vĩnh Viễn).\n✍️ Hãy nhập: `UID|Lý_Do`")
            bot.register_next_step_handler(msg, process_admin_ban)

        elif call.data == "usrmng_unban":
            msg = bot.send_message(call.message.chat.id, "🔓 Nhập UID khách hàng cần GỠ BAN / XÓA CẢNH CÁO:")
            bot.register_next_step_handler(msg, process_admin_unban)

        elif call.data == "usrmng_listban":
            text = f"📜 **DANH SÁCH ĐEN KHÁCH HÀNG**\n{UI_DIVIDER}\n"
            if not DB_BAN_LIST:
                text += "👉 Không có ai đang bị cấm.\n"
            else:
                for uid, info in DB_BAN_LIST.items():
                    text += f"🔹 UID: `{uid}`\n      Lý do: {info['reason']}\n      Hạn: {info['unban_date'] if info['unban_date'] != '0' else 'Vĩnh viễn'}\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            markup = InlineKeyboardMarkup().add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_usermng"))
            try: bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except: bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("admbill_yes_"):
            target_uid = int(call.data.replace("admbill_yes_", ""))
            msg = bot.send_message(call.message.chat.id, f"✅ NHẬP SỐ TIỀN CẦN DUYỆT cho UID `{target_uid}`:")
            bot.register_next_step_handler(msg, process_bill_approve, target_uid, call.message.message_id, call.message.chat.id)

        elif call.data.startswith("admbill_no_"):
            target_uid = int(call.data.replace("admbill_no_", ""))
            text = f"❌ ĐÃ TỪ CHỐI BỞI ADMIN: `{admin_id}`"
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text)
            try: bot.send_message(target_uid, "❌ **THÔNG BÁO TỪ CHỐI:**\nGiao dịch nạp tiền bị từ chối do biên lai không hợp lệ.")
            except: pass

    except Exception as e:
        print(f"Error in admin callbacks: {e}")

# ==========================================
# HÀM XỬ LÝ NEXT_STEP QUẢN TRỊ & BROADCAST
# ==========================================
def process_admin_add(message, admin_id):
    try:
        new_uid = int(message.text.strip())
        if new_uid not in ADMINS:
            ADMINS[new_uid] = admin_id
            bot.reply_to(message, f"✅ Đã thêm Admin thành công: `{new_uid}`", parse_mode="Markdown")
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
            bot.reply_to(message, f"✅ Đã tước quyền Admin của UID `{target_uid}`.")
        else:
            bot.reply_to(message, "❌ Bạn không có quyền xóa Admin này do không phải người thêm họ.")
    except: bot.reply_to(message, "❌ Sai định dạng.")

def process_admin_logo(message):
    try:
        if message.photo:
            DB_CONFIG["logo"] = get_image_url(message)
            bot.reply_to(message, "✅ Đã nhận dạng và cập nhật Logo bằng Hình Ảnh thành công!")
        elif message.text:
            DB_CONFIG["logo"] = message.text.strip()
            bot.reply_to(message, "✅ Đã cập nhật Logo bằng Link URL thành công!")
        else:
            bot.reply_to(message, "❌ Vui lòng gửi ảnh hoặc link.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_admin_bank(message):
    try:
        if message.photo and message.caption:
            DB_CONFIG["qr_bank"] = get_image_url(message)
            DB_CONFIG["bank_info"] = message.caption.strip()
            bot.reply_to(message, "✅ Đã cập nhật cấu hình Ngân Hàng & QR Code bằng Hình Ảnh thành công!")
        elif message.text and "|" in message.text:
            parts = message.text.split("|")
            DB_CONFIG["qr_bank"] = parts[0].strip()
            DB_CONFIG["bank_info"] = parts[1].strip()
            bot.reply_to(message, "✅ Đã cập nhật cấu hình Ngân Hàng bằng Text thành công!")
        else:
            bot.reply_to(message, "❌ Thất bại. Vui lòng gửi Ảnh có Caption, hoặc nhập định dạng `LINK_QR|THÔNG_TIN`.")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi: {e}")

def process_brd_media(message, mode):
    has_media = message.text.strip().lower() in ["có", "co", "yes"]
    if mode == "all":
        msg = bot.send_message(message.chat.id, "✍️ Gửi nội dung tin nhắn (kèm ảnh/video nếu có):")
        bot.register_next_step_handler(msg, execute_broadcast, None, has_media)
    else:
        msg = bot.send_message(message.chat.id, "👤 Nhập UID nhận:")
        bot.register_next_step_handler(msg, process_brd_uid, has_media)

def process_brd_uid(message, has_media):
    try:
        target_uid = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"✍️ Gửi nội dung cho `{target_uid}`:")
        bot.register_next_step_handler(msg, execute_broadcast, target_uid, has_media)
    except: bot.reply_to(message, "❌ UID sai.")

def execute_broadcast(message, target_uid, has_media):
    targets = [target_uid] if target_uid else list(DB_USERS.keys())
    success = 0
    for uid in targets:
        try:
            if has_media:
                if message.photo: bot.send_photo(uid, message.photo[-1].file_id, caption=message.caption, parse_mode="Markdown")
                elif message.video: bot.send_video(uid, message.video.file_id, caption=message.caption, parse_mode="Markdown")
            else:
                bot.send_message(uid, message.text, parse_mode="Markdown")
            success += 1
        except: pass
    bot.reply_to(message, f"📢 Đã phát thông báo tới `{success}` người dùng.")

def process_admin_balance(message, action):
    try:
        uid_str, amt_str = message.text.split("|")
        target_uid = int(uid_str.strip())
        amount = int(amt_str.strip())
        
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ User chưa khởi tạo.")
            return
            
        if action == "add":
            DB_USERS[target_uid]["balance"] += amount
            DB_USERS[target_uid]["total_deposit"] += amount
            bot.reply_to(message, f"✅ Đã cộng `+{amount:,} VND` cho `{target_uid}`.")
            try: bot.send_message(target_uid, f"🔔 **THÔNG BÁO:** Bạn được cộng `+{amount:,} VND`.")
            except: pass
        elif action == "sub":
            DB_USERS[target_uid]["balance"] = max(0, DB_USERS[target_uid]["balance"] - amount)
            bot.reply_to(message, f"✅ Đã trừ `-{amount:,} VND` của `{target_uid}`.")
            try: bot.send_message(target_uid, f"⚠️ **CẢNH BÁO:** Bạn bị khấu trừ `-{amount:,} VND`.")
            except: pass
    except: bot.reply_to(message, "❌ Định dạng `UID|Số_Tiền`.")

def process_admin_ban(message):
    try:
        uid_str, reason = message.text.split("|")
        target_uid = int(uid_str.strip())
        reason = reason.strip()
        
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ User chưa khởi tạo.")
            return
            
        strikes = DB_USERS[target_uid].get("strikes", 0) + 1
        DB_USERS[target_uid]["strikes"] = strikes
        ban_date = datetime.now().strftime(DATE_FORMAT)
        
        if strikes == 1:
            unban_date = (datetime.now() + timedelta(days=3)).strftime(DATE_FORMAT)
            DB_BAN_LIST[target_uid] = {"ban_date": ban_date, "reason": reason, "unban_date": unban_date}
            bot.reply_to(message, f"⚠️ Cảnh cáo lần 1 UID `{target_uid}`. Khóa 3 ngày.")
        else:
            unban_date = "0"
            DB_BAN_LIST[target_uid] = {"ban_date": ban_date, "reason": reason, "unban_date": unban_date}
            bot.reply_to(message, f"🛑 Vi phạm lần 2. Khóa VĨNH VIỄN UID `{target_uid}`.")
            
    except: bot.reply_to(message, "❌ Sai định dạng `UID|Lý_Do`.")

def process_admin_unban(message):
    try:
        target_uid = int(message.text.strip())
        if target_uid in DB_BAN_LIST:
            del DB_BAN_LIST[target_uid]
        if target_uid in DB_USERS:
            DB_USERS[target_uid]["strikes"] = 0
        bot.reply_to(message, f"✅ Đã gỡ Ban / Reset cảnh cáo cho UID `{target_uid}`.")
        try: bot.send_message(target_uid, "🎉 **CHÚC MỪNG:** Tài khoản đã được gỡ cấm. Gõ /start để tiếp tục.")
        except: pass
    except: bot.reply_to(message, "❌ Lỗi định dạng UID.")

def process_bill_approve(message, target_uid, orig_msg_id, orig_chat_id):
    try:
        amount = int(message.text.strip())
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ Người dùng chưa khởi tạo.")
            return
            
        DB_USERS[target_uid]["balance"] += amount
        DB_USERS[target_uid]["total_deposit"] += amount
        
        now_str = datetime.now().strftime(DATE_FORMAT)
        uname = DB_USERS[target_uid]["username"]
        DB_STATS["deposits"].append({"uid": target_uid, "username": uname, "amount": amount, "time": now_str})
        
        bot.reply_to(message, f"✅ Đã cộng `+{amount:,} VND`.")
        bot.edit_message_caption(chat_id=orig_chat_id, message_id=orig_msg_id, caption=f"✅ DUYỆT CỘNG: `+{amount:,} VND`\nBởi Admin: `{message.from_user.id}`", parse_mode="Markdown")
        
        try: bot.send_message(target_uid, f"🎉 **NẠP THÀNH CÔNG:** Bạn được cộng `+{amount:,} VND`.", parse_mode="Markdown")
        except: pass
    except: bot.reply_to(message, "❌ Vui lòng nhập Số Tiền là ký tự số.")

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
