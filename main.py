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
API_TOKEN = os.environ.get("TELEGRAM_TOKEN", "7123456789:ABCdefGhIJKlmNoPQRsTUVwXyZ12345")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "https://mail24h-bot.onrender.com")
WEBHOOK_URL = f"{WEBHOOK_HOST}/{API_TOKEN}/"
PORT = int(os.environ.get("PORT", 5000))

bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)

# ==========================================
# CƠ SỞ DỮ LIỆU GIẢ LẬP TRONG BỘ NHỚ (GLOBAL DICTIONARY)
# ==========================================
ADMINS = [123456789] 

DB_USERS = {}
DB_BAN_LIST = {}
DB_CONFIG = {
    "logo": "https://imgur.com/your-logo.jpg",
    "qr_bank": "https://api.vietqr.io/image/970422-190365899999-YL66FmK.jpg",
    "bank_info": "STK: 123456789\nNgân Hàng: MB Bank\nChủ Tài Khoản: NGUYEN VAN A"
}
DB_REVENUE = {
    "total_deposit": 0,
    "total_rent": 0,
    "users_today": set()
}

DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
UI_DIVIDER = "══════════════════════"
UI_FOOTER = "🔒 Chỉ dành cho thành viên thuộc DKGROUP"

# ==========================================
# GIAO TIẾP API TEMPMAIL.NINJA MÔ PHỎNG (SỬ DỤNG REQUESTS)
# ==========================================
def call_mail_api(endpoint, method="POST", data=None):
    url = f"https://tempmail.ninja/api/v1/{endpoint}"
    headers = {"Content-Type": "application/json"}
    try:
        if method == "POST":
            # Trong thực tế: response = requests.post(url, json=data, headers=headers, timeout=10)
            # return response.json()
            pass
        elif method == "GET":
            # Trong thực tế: response = requests.get(url, params=data, headers=headers, timeout=10)
            # return response.json()
            pass
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def buy_mail_account():
    call_mail_api("emails/create", method="POST", data={"domain": "tempmail.ninja"})
    rand_prefix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    email_address = f"{rand_prefix}@tempmail.ninja"
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
    today_str = datetime.now().strftime("%Y-%m-%d")
    DB_REVENUE["users_today"].add(user_id)
    if user_id not in DB_USERS:
        DB_USERS[user_id] = {
            "username": username if username else f"User_{user_id}",
            "balance": 0,
            "total_deposit": 0,
            "current_mail": {},
            "history_mails": []
        }
    else:
        DB_USERS[user_id]["username"] = username if username else f"User_{user_id}"

# ==========================================
# PHÂN HỆ NGƯỜI DÙNG (USER INTERFACE)
# ==========================================
def ui_user_main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📧 Thuê Mail", callback_data="usr_rent"),
        InlineKeyboardButton("💳 Nạp Tiền", callback_data="usr_deposit"),
        InlineKeyboardButton("👤 Tài Khoản", callback_data="usr_profile"),
        InlineKeyboardButton("📞 Liên Hệ", callback_data="usr_contact")
    )
    return markup

@bot.message_handler(commands=['start'])
def command_start(message):
    try:
        user_id = message.from_user.id
        is_banned, b_date, reason, u_date = check_ban(user_id)
        if is_banned:
            text = (
                f"🚫 **TÀI KHOẢN BỊ CẤM**\n"
                f"{UI_DIVIDER}\n"
                f"📆 Ngày khóa: `{b_date}`\n"
                f"🛑 Lý do: `{reason}`\n"
                f"⏳ Hạn mở khóa: `{u_date}`\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.send_message(message.chat.id, text, parse_mode="Markdown")
            return
            
        init_user(user_id, message.from_user.username)
        u_data = DB_USERS[user_id]
        
        text = (
            f"⚡ **HỆ THỐNG MAIL 24H**\n"
            f"{UI_DIVIDER}\n"
            f"👋 Xin chào, **{u_data['username']}**!\n"
            f"💰 Số dư: `{u_data['balance']:,} VND`\n\n"
            f"📌 Vui lòng chọn chức năng thao tác bên dưới:\n"
            f"{UI_DIVIDER}\n"
            f"{UI_FOOTER}"
        )
        bot.send_photo(message.chat.id, photo=DB_CONFIG["logo"], caption=text, reply_markup=ui_user_main_menu(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error in start: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('usr_') or call.data == 'usr_main')
def user_callbacks(call):
    try:
        user_id = call.from_user.id
        is_banned, b_date, reason, u_date = check_ban(user_id)
        if is_banned:
            bot.answer_callback_query(call.id, f"Tài khoản bị khóa đến {u_date}", show_alert=True)
            return
            
        init_user(user_id, call.from_user.username)
        u_data = DB_USERS[user_id]

        if call.data == "usr_main":
            text = (
                f"⚡ **HỆ THỐNG MAIL 24H**\n"
                f"{UI_DIVIDER}\n"
                f"👋 Xin chào, **{u_data['username']}**!\n"
                f"💰 Số dư: `{u_data['balance']:,} VND`\n\n"
                f"📌 Vui lòng chọn chức năng thao tác bên dưới:\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.edit_message_media(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["logo"], caption=text, parse_mode="Markdown"),
                reply_markup=ui_user_main_menu()
            )

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
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")

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
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Tài Khoản", callback_data="usr_profile"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("usr_histdetail_"):
            order_id = call.data.split("_")[2]
            mail_item = next((item for item in u_data['history_mails'] if item['order_id'] == order_id), None)
            
            if mail_item:
                rent_time = datetime.strptime(mail_item['time'], DATE_FORMAT)
                is_active = (datetime.now() - rent_time).total_seconds() < 86400 and u_data.get('current_mail', {}).get('order_id') == order_id
                
                status = "✅ Đang hoạt động" if is_active else "❌ Đã hết hạn / Bị thay thế"
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
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "usr_contact":
            text = (
                f"📞 **THÔNG TIN HỖ TRỢ**\n"
                f"{UI_DIVIDER}\n"
                f"🌐 Website: `https://tempmail.ninja`\n"
                f"💬 Kênh hỗ trợ trực tuyến 24/7.\n"
                f"✉️ Mọi khiếu nại nạp tiền, lỗi dịch vụ vui lòng liên hệ trực tiếp đội ngũ Admin.\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "usr_rent":
            if u_data['balance'] < 1000:
                bot.answer_callback_query(call.id, "❌ Số dư không đủ 1,000 VND. Vui lòng nạp thêm!", show_alert=True)
                return
            
            if 'active' in u_data.get('current_mail', {}):
                u_data['current_mail']['active'] = False
            
            u_data['balance'] -= 1000
            DB_REVENUE['total_rent'] += 1000
            
            new_email, order_id = buy_mail_account()
            rent_time = datetime.now().strftime(DATE_FORMAT)
            
            mail_record = {
                "email": new_email,
                "order_id": order_id,
                "time": rent_time,
                "active": True
            }
            
            u_data['current_mail'] = mail_record
            u_data['history_mails'].append(mail_record)
            
            text = (
                f"✅ **GIAO DỊCH THUÊ MAIL THÀNH CÔNG**\n"
                f"{UI_DIVIDER}\n"
                f"📧 Email Mới: `{new_email}`\n"
                f"🆔 Mã Đơn: `{order_id}`\n"
                f"🕒 Kích hoạt lúc: `{rent_time}`\n\n"
                f"⚠️ *Lưu ý: Bạn có 24h để sử dụng Mail này. Việc thuê mail khác sẽ làm vô hiệu hóa lập tức mail hiện tại!*\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Nhận Mã OTP (Phí 1,000đ)", callback_data=f"usr_getotp_{order_id}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("usr_getotp_"):
            order_id = call.data.split("_")[2]
            current = u_data.get('current_mail', {})
            
            if not current or current.get('order_id') != order_id or not current.get('active'):
                bot.answer_callback_query(call.id, "❌ Email này đã bị thay thế hoặc vô hiệu hóa!", show_alert=True)
                return
                
            rent_time = datetime.strptime(current['time'], DATE_FORMAT)
            if (datetime.now() - rent_time).total_seconds() >= 86400:
                current['active'] = False
                bot.answer_callback_query(call.id, "❌ Email này đã vượt quá 24h và hết hạn sử dụng!", show_alert=True)
                return
                
            if u_data['balance'] < 1000:
                bot.answer_callback_query(call.id, "❌ Số dư không đủ 1,000 VND để nhận OTP!", show_alert=True)
                return
                
            u_data['balance'] -= 1000
            DB_REVENUE['total_rent'] += 1000
            
            otp_code = get_mail_otp(order_id)
            
            text = (
                f"🔄 **KẾT QUẢ QUÉT MÃ OTP**\n"
                f"{UI_DIVIDER}\n"
                f"📧 Email: `{current['email']}`\n"
                f"🔑 Mã Kích Hoạt (OTP): **{otp_code}**\n"
                f"🕒 Quét lúc: `{datetime.now().strftime(DATE_FORMAT)}`\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Nhận Mã OTP (Phí 1,000đ)", callback_data=f"usr_getotp_{order_id}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                bot.answer_callback_query(call.id, "Đã quét nhưng chưa có tin nhắn mới hơn.", show_alert=False)

        elif call.data == "usr_deposit":
            memo_str = f"MAIL24H {user_id} {''.join(random.choices(string.ascii_uppercase, k=4))}"
            text = (
                f"🏦 **CỔNG NẠP TIỀN TỰ ĐỘNG**\n"
                f"{UI_DIVIDER}\n"
                f"{DB_CONFIG['bank_info']}\n"
                f"📝 Nội dung chuyển khoản:\n`{memo_str}`\n\n"
                f"⚠️ **CẢNH BÁO QUAN TRỌNG:**\n"
                f"Tuyệt đối không gửi biên lai giả mạo (Fake Bill). Hệ thống tự động quét và khóa tài khoản vĩnh viễn nếu phát hiện gian lận.\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📸 Gửi Bill Xác Nhận", callback_data=f"usr_sendbill_{memo_str}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="usr_main"))
            
            bot.edit_message_media(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["qr_bank"], caption=text, parse_mode="Markdown"),
                reply_markup=markup
            )

        elif call.data.startswith("usr_sendbill_"):
            memo_str = call.data.replace("usr_sendbill_", "")
            msg = bot.send_message(call.message.chat.id, f"📸 **YÊU CẦU:**\nVui lòng GỬI ẢNH CHỤP MÀN HÌNH giao dịch thành công của bạn lên đây để xác nhận nạp tiền cho nội dung: `{memo_str}`.", parse_mode="Markdown")
            bot.register_next_step_handler(msg, process_user_bill, memo_str)

    except Exception as e:
        print(f"Error in user callbacks: {e}")

def process_user_bill(message, memo_str):
    try:
        user_id = message.from_user.id
        if not message.photo:
            bot.reply_to(message, "❌ Bắt buộc phải là hình ảnh (Photo). Vui lòng thực hiện lại yêu cầu nạp tiền.")
            return
            
        photo_id = message.photo[-1].file_id
        username = DB_USERS[user_id]["username"]
        
        text_admin = (
            f"🔔 **YÊU CẦU DUYỆT NẠP MỚI**\n"
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
        
        for admin_id in ADMINS:
            try:
                bot.send_photo(chat_id=admin_id, photo=photo_id, caption=text_admin, reply_markup=markup_admin, parse_mode="Markdown")
            except Exception:
                pass
                
        bot.reply_to(message, "✅ **HOÀN TẤT:** Hình ảnh giao dịch đã được chuyển tới Ban Quản Trị. Vui lòng chờ phê duyệt.")
    except Exception as e:
        print(f"Error process user bill: {e}")

# ==========================================
# PHÂN HỆ QUẢN TRỊ VIÊN (ADMIN INTERFACE)
# ==========================================
def ui_admin_main_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Thêm Admin Mới", callback_data="adm_add"),
        InlineKeyboardButton("📋 Xem Danh Sách Admin", callback_data="adm_list"),
        InlineKeyboardButton("🖼️ Đổi Logo Bot", callback_data="adm_logo"),
        InlineKeyboardButton("🏦 Đổi Cấu Hình Bank & QR", callback_data="adm_bank"),
        InlineKeyboardButton("📊 Xem Doanh Thu", callback_data="adm_revenue"),
        InlineKeyboardButton("👥 Xem User Hôm Hiện Tại", callback_data="adm_users_today"),
        InlineKeyboardButton("🔍 Quản Lý User", callback_data="adm_usermng")
    )
    return markup

def ui_admin_user_menu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 Cộng Tiền", callback_data="usrmng_add"),
        InlineKeyboardButton("📉 Trừ Tiền", callback_data="usrmng_sub"),
        InlineKeyboardButton("🚫 Ban User", callback_data="usrmng_ban"),
        InlineKeyboardButton("🔓 Unban User", callback_data="usrmng_unban"),
        InlineKeyboardButton("📜 Danh Sách Ban", callback_data="usrmng_listban"),
        InlineKeyboardButton("⬅️ Quay Lại Tối Cao", callback_data="adm_main")
    )
    return markup

@bot.message_handler(commands=['admin'])
def command_admin(message):
    try:
        user_id = message.from_user.id
        if user_id not in ADMINS:
            return
            
        text = (
            f"👑 **BẢNG ĐIỀU HÀNH TỐI CAO ADMIN**\n"
            f"{UI_DIVIDER}\n"
            f"👤 Admin ID: `{user_id}`\n"
            f"📌 Lựa chọn tác vụ quản trị nghiệp vụ phía dưới:\n"
            f"{UI_DIVIDER}\n"
            f"{UI_FOOTER}"
        )
        bot.send_message(message.chat.id, text, reply_markup=ui_admin_main_menu(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error command admin: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm_') or call.data.startswith('usrmng_') or call.data.startswith('admbill_'))
def admin_callbacks(call):
    try:
        admin_id = call.from_user.id
        if admin_id not in ADMINS:
            bot.answer_callback_query(call.id, "Từ chối quyền truy cập!", show_alert=True)
            return

        if call.data == "adm_main":
            text = (
                f"👑 **BẢNG ĐIỀU HÀNH TỐI CAO ADMIN**\n"
                f"{UI_DIVIDER}\n"
                f"👤 Admin ID: `{admin_id}`\n"
                f"📌 Lựa chọn tác vụ quản trị nghiệp vụ phía dưới:\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=ui_admin_main_menu(), parse_mode="Markdown")

        elif call.data == "adm_add":
            msg = bot.send_message(call.message.chat.id, "✍️ Vui lòng nhập UID Telegram của Admin mới:")
            bot.register_next_step_handler(msg, process_admin_add)

        elif call.data == "adm_list":
            text = f"📋 **DANH SÁCH QUẢN TRỊ VIÊN**\n{UI_DIVIDER}\n"
            for idx, adm_id in enumerate(ADMINS, 1):
                text += f"{idx}. UID: `{adm_id}`\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "adm_logo":
            msg = bot.send_message(call.message.chat.id, "✍️ Vui lòng nhập đường link URL của ảnh Logo mới:")
            bot.register_next_step_handler(msg, process_admin_logo)

        elif call.data == "adm_bank":
            msg = bot.send_message(call.message.chat.id, "🏦 Nhập cấu hình Ngân hàng theo định dạng chính xác:\n`LINK_ẢNH_QR|VĂN_BẢN_NGÂN_HÀNG`\n\nVí dụ:\n`https://imgur.com/x.jpg|STK: 1234\nNgân Hàng: MB\nChủ: ABC`")
            bot.register_next_step_handler(msg, process_admin_bank)

        elif call.data == "adm_revenue":
            text = (
                f"📊 **BÁO CÁO DOANH THU & THỐNG KÊ**\n"
                f"{UI_DIVIDER}\n"
                f"💰 Tổng Tiền Nạp: `{DB_REVENUE['total_deposit']:,} VND`\n"
                f"📧 Tổng Tiền Thuê: `{DB_REVENUE['total_rent']:,} VND`\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "adm_users_today":
            text = (
                f"👥 **THỐNG KÊ TƯƠNG TÁC NGÀY**\n"
                f"{UI_DIVIDER}\n"
                f"📈 Số lượng Users tương tác: `{len(DB_REVENUE['users_today'])}` người.\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_main"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "adm_usermng":
            text = (
                f"🔍 **DANH MỤC QUẢN LÝ KHÁCH HÀNG**\n"
                f"{UI_DIVIDER}\n"
                f"📌 Lựa chọn công cụ xử lý Users:\n"
                f"{UI_DIVIDER}\n"
                f"{UI_FOOTER}"
            )
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=ui_admin_user_menu(), parse_mode="Markdown")

        elif call.data == "usrmng_add":
            msg = bot.send_message(call.message.chat.id, "💵 Nhập cấu trúc để CỘNG TIỀN:\n`UID|Số_Tiền`")
            bot.register_next_step_handler(msg, process_admin_balance, "add")

        elif call.data == "usrmng_sub":
            msg = bot.send_message(call.message.chat.id, "📉 Nhập cấu trúc để TRỪ TIỀN:\n`UID|Số_Tiền`")
            bot.register_next_step_handler(msg, process_admin_balance, "sub")

        elif call.data == "usrmng_ban":
            msg = bot.send_message(call.message.chat.id, "🚫 Nhập cấu trúc để BAN KHÁCH HÀNG:\n`UID|Lý_Do|Số_Ngày`\n(Ghi Số_Ngày là 0 để khóa vĩnh viễn)")
            bot.register_next_step_handler(msg, process_admin_ban)

        elif call.data == "usrmng_unban":
            msg = bot.send_message(call.message.chat.id, "🔓 Nhập UID khách hàng cần GỠ BAN:")
            bot.register_next_step_handler(msg, process_admin_unban)

        elif call.data == "usrmng_listban":
            text = f"📜 **DANH SÁCH ĐEN KHÁCH HÀNG**\n{UI_DIVIDER}\n"
            if not DB_BAN_LIST:
                text += "👉 Không có khách hàng nào đang bị cấm.\n"
            else:
                for uid, info in DB_BAN_LIST.items():
                    text += f"🔹 UID: `{uid}`\n      Lý do: {info['reason']}\n      Hạn: {info['unban_date'] if info['unban_date'] != '0' else 'Vĩnh viễn'}\n"
            text += f"{UI_DIVIDER}\n{UI_FOOTER}"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="adm_usermng"))
            bot.edit_message_text(text, chat_id=call.message.chat.id, message_id=call.message.message_id, reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("admbill_yes_"):
            target_uid = int(call.data.replace("admbill_yes_", ""))
            msg = bot.send_message(call.message.chat.id, f"✅ NHẬP SỐ TIỀN CẦN DUYỆT cho UID `{target_uid}`:")
            bot.register_next_step_handler(msg, process_bill_approve, target_uid, call.message.message_id, call.message.chat.id)

        elif call.data.startswith("admbill_no_"):
            target_uid = int(call.data.replace("admbill_no_", ""))
            text = f"❌ ĐÃ TỪ CHỐI BỞI ADMIN: `{admin_id}`"
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=text)
            try:
                bot.send_message(target_uid, "❌ **THÔNG BÁO TỪ CHỐI:**\nGiao dịch nạp tiền của bạn đã bị từ chối do sai cấu trúc hoặc biên lai không hợp lệ.")
            except Exception:
                pass

    except Exception as e:
        print(f"Error in admin callbacks: {e}")

# ==========================================
# CÁC HÀM XỬ LÝ NEXT_STEP QUẢN TRỊ
# ==========================================
def process_admin_add(message):
    try:
        new_admin = int(message.text.strip())
        if new_admin not in ADMINS:
            ADMINS.append(new_admin)
            bot.reply_to(message, f"✅ Đã thêm đặc quyền Admin cho UID: `{new_admin}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ UID này đã là Admin!")
    except Exception:
        bot.reply_to(message, "❌ Dữ liệu nhập vào phải là một ID số tự nhiên.")

def process_admin_logo(message):
    try:
        DB_CONFIG["logo"] = message.text.strip()
        bot.reply_to(message, "✅ Đã cập nhật Logo thành công!")
    except Exception:
        bot.reply_to(message, "❌ Lỗi hệ thống khi cập nhật Logo.")

def process_admin_bank(message):
    try:
        parts = message.text.split("|")
        DB_CONFIG["qr_bank"] = parts[0].strip()
        DB_CONFIG["bank_info"] = parts[1].strip()
        bot.reply_to(message, "✅ Đã cập nhật cấu hình Ngân Hàng & QR Code thành công!")
    except Exception:
        bot.reply_to(message, "❌ Sai cấu trúc yêu cầu phân tách bằng dấu |")

def process_admin_balance(message, action):
    try:
        uid_str, amt_str = message.text.split("|")
        target_uid = int(uid_str.strip())
        amount = int(amt_str.strip())
        
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ User chưa tồn tại trong hệ thống (chưa /start).")
            return
            
        if action == "add":
            DB_USERS[target_uid]["balance"] += amount
            DB_USERS[target_uid]["total_deposit"] += amount
            DB_REVENUE["total_deposit"] += amount
            bot.reply_to(message, f"✅ Đã cộng `+{amount:,} VND` vào ví của `{target_uid}`.", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, f"🔔 **THÔNG BÁO SỐ DƯ:**\nTài khoản của bạn đã được cộng `+{amount:,} VND` từ quản trị viên.", parse_mode="Markdown")
            except Exception:
                pass
        elif action == "sub":
            DB_USERS[target_uid]["balance"] -= amount
            if DB_USERS[target_uid]["balance"] < 0:
                DB_USERS[target_uid]["balance"] = 0
            bot.reply_to(message, f"✅ Đã trừ `-{amount:,} VND` khỏi ví của `{target_uid}`.", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, f"⚠️ **CẢNH BÁO SỐ DƯ:**\nTài khoản của bạn đã bị khấu trừ `-{amount:,} VND` từ quản trị viên.", parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        bot.reply_to(message, "❌ Sai cấu trúc định dạng yêu cầu.")

def process_admin_ban(message):
    try:
        uid_str, reason, days_str = message.text.split("|")
        target_uid = int(uid_str.strip())
        days = int(days_str.strip())
        
        ban_date = datetime.now().strftime(DATE_FORMAT)
        if days == 0:
            unban_date = "0"
        else:
            unban_date = (datetime.now() + timedelta(days=days)).strftime(DATE_FORMAT)
            
        DB_BAN_LIST[target_uid] = {
            "ban_date": ban_date,
            "reason": reason.strip(),
            "unban_date": unban_date
        }
        bot.reply_to(message, f"✅ Đã Ban UID `{target_uid}` thành công.", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Sai định dạng `UID|Lý_Do|Số_Ngày`.")

def process_admin_unban(message):
    try:
        target_uid = int(message.text.strip())
        if target_uid in DB_BAN_LIST:
            del DB_BAN_LIST[target_uid]
            bot.reply_to(message, f"✅ Đã gỡ Ban UID `{target_uid}` thành công.", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, "🎉 **CHÚC MỪNG:**\nTài khoản của bạn đã được xóa khỏi danh sách đen. Gõ /start để tiếp tục.")
            except Exception:
                pass
        else:
            bot.reply_to(message, "⚠️ User này không bị Ban.")
    except Exception:
        bot.reply_to(message, "❌ Lỗi định dạng UID.")

def process_bill_approve(message, target_uid, orig_msg_id, orig_chat_id):
    try:
        amount = int(message.text.strip())
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ Thất bại: Người dùng chưa khởi tạo trên DB.")
            return
            
        DB_USERS[target_uid]["balance"] += amount
        DB_USERS[target_uid]["total_deposit"] += amount
        DB_REVENUE["total_deposit"] += amount
        
        bot.reply_to(message, f"✅ Xử lý thành công hóa đơn: `+{amount:,} VND`.")
        
        text = f"✅ ĐÃ DUYỆT BỞI ADMIN: `{message.from_user.id}`\n💰 Cấp phát: `+{amount:,} VND`."
        bot.edit_message_caption(chat_id=orig_chat_id, message_id=orig_msg_id, caption=text, parse_mode="Markdown")
        
        try:
            bot.send_message(target_uid, f"🎉 **NẠP TIỀN THÀNH CÔNG:**\nGiao dịch của bạn đã được duyệt. Ví đã được cộng thêm `+{amount:,} VND`.", parse_mode="Markdown")
        except Exception:
            pass
    except Exception:
        bot.reply_to(message, "❌ Vui lòng nhập Số Tiền là ký tự số hợp lệ.")

# ==========================================
# KHỞI CHẠY KIẾN TRÚC WEBHOOK FLASK VÀ RENDERS
# ==========================================
@app.route('/', methods=['GET', 'HEAD'])
def health_check():
    return "Hệ thống Bot Mail 24H đang vận hành trực tuyến!", 200

@app.route(f'/{API_TOKEN}/', methods=['POST'])
def receive_updates():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

if __name__ == '__main__':
    # Giải phóng memory cache webhook tồn đọng theo yêu cầu nghiêm ngặt
    bot.remove_webhook()
    time.sleep(1)
    # Khai báo địa chỉ mới trực tiếp cho telegram
    bot.set_webhook(url=WEBHOOK_URL)
    
    # Treo luồng Port trên Render.com
    app.run(host="0.0.0.0", port=PORT)
