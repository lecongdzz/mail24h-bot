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
# CẤU HÌNH BIẾN MÔI TRƯỜNG & TOKENS
# ==========================================
API_TOKEN = os.getenv("TELEGRAM_TOKEN", "7123456789:ABCdefGhIJKlmNoPQRsTUVwXyZ12345")
# Link Webhook cần đổi thành link app của bạn trên Render, ví dụ: https://mail24h.onrender.com
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "https://your-domain.onrender.com")
WEBHOOK_URL = f"{WEBHOOK_HOST}/{API_TOKEN}/"
PORT = int(os.getenv("PORT", 5000))

bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)

# ==========================================
# CƠ SỞ DỮ LIỆU GIẢ LẬP TRONG BỘ NHỚ ĐỆM (GLOBAL DICT)
# ==========================================
ADMINS = [6123456789]  # Thay UID Admin gốc của bạn vào đây

DB_CONFIG = {
    "banner_url": "https://images.unsplash.com/photo-1557200134-90327ee9fafa?w=800", # Link placeholder đẹp
    "brand_name": "MAIL 24H Powered By DK Group",
    "group_name": "Đoàn Kết MMO Group",
    "web_url": "https://tangtuongtacsieure.com",
    "api_key": "MOCK_API_KEY_123456789_XYZ",
    "admin_contact": "@tangtuongtacsieureadmin",
    "support_contact": "@Lecongdzzz",
    "price_per_day": 1000,
    "min_deposit": 10000,
    "bank_name": "MB BANK (Ngân Hàng Quân Đội)",
    "bank_account": "190365899999",
    "bank_holder": "DOAN KET MMO GROUP",
    "bank_qr": "https://api.vietqr.io/image/970422-190365899999-YL66FmK.jpg", # QR mẫu
    "welcome_text": "Chào mừng bạn đến với hệ thống Thuê Mail tự động 24/7!"
}

DB_USERS = {
    # Mẫu cấu trúc User:
    # 12345678: {
    #    "username": "user1", "balance": 50000, "total_deposit": 50000,
    #    "joined_date": "2026-06-21", "history": []
    # }
}

DB_BAN_LIST = {
    # 87654321: {"reason": "Spam bill", "expiry": "2026-06-22 12:00:00"} # Hoặc "Vĩnh Viễn"
}

# Lưu lịch sử doanh thu mô phỏng
DB_REVENUE = {
    "deposit_today": 0,
    "rent_today": 0,
    "new_users_today": set()
}

# Lưu danh sách Giftcode hoạt động
DB_GIFTCODES = {
    "DKGROUP2026": {"amount": 20000, "count": 100, "used_by": []}
}

# ==========================================
# CÁC HÀM TIỆN ÍCH & BACKGROUND WORKERS
# ==========================================
def check_ban_status(user_id):
    """Kiểm tra xem User có bị ban không, tự động mở ban nếu hết hạn"""
    if user_id in DB_BAN_LIST:
        expiry = DB_BAN_LIST[user_id]["expiry"]
        if expiry == "Vĩnh Viễn":
            return True, "Vĩnh Viễn", DB_BAN_LIST[user_id]["reason"]
        
        try:
            expiry_dt = datetime.strptime(expiry, "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_dt:
                del DB_BAN_LIST[user_id]
                return False, None, None
            else:
                return True, expiry, DB_BAN_LIST[user_id]["reason"]
        except Exception:
            return True, "Không xác định", DB_BAN_LIST[user_id]["reason"]
    return False, None, None

def init_user_if_not_exists(user):
    """Khởi tạo thông tin user nếu lần đầu tương tác"""
    uid = user.id
    username = user.username if user.username else f"User_{uid}"
    
    # Ghi nhận user mới trong ngày
    today_str = datetime.now().strftime("%Y-%m-%d")
    DB_REVENUE["new_users_today"].add(uid)
    
    if uid not in DB_USERS:
        DB_USERS[uid] = {
            "username": username,
            "balance": 0,
            "total_deposit": 0,
            "joined_date": today_str,
            "history": [] # Lưu danh sách mail đã thuê
        }
    else:
        # Cập nhật lại username nếu có thay đổi
        DB_USERS[uid]["username"] = username

def generate_deposit_code(username):
    """Tạo nội dung chuyển khoản ngẫu nhiên theo định dạng cấu trúc đề bài"""
    rand_digit = random.choice(string.digits)
    rand_word = ''.join(random.choices(string.ascii_uppercase, k=4))
    return f"{username.upper()} {rand_digit} {rand_word}"

# ==========================================
# KẾT NỐI API WEB DỊCH VỤ TANGTUONGTACSIEURE.COM
# ==========================================
def api_get_mail_list(service_type="all"):
    """Khung hàm lấy danh sách Mail từ Web đối tác"""
    url = f"{DB_CONFIG['web_url']}/api/mail/list"
    headers = {"Authorization": f"Bearer {DB_CONFIG['api_key']}"}
    params = {"service": service_type}
    try:
        # Trong thực tế, bạn sẽ bỏ comment dòng dưới:
        # response = requests.get(url, headers=headers, params=params, timeout=10)
        # return response.json()
        
        # Mock dữ liệu trả về phục vụ chạy thử nghiệm không lỗi:
        return {
            "status": "success",
            "data": [
                {"mail": "dkgroup_test1@gmail.com", "app": "Facebook", "price": DB_CONFIG['price_per_day']},
                {"mail": "dkgroup_test2@hotmail.com", "app": "Telegram", "price": DB_CONFIG['price_per_day']}
            ]
        }
    except Exception as e:
        print(f"Lỗi API Get Mail: {e}")
        return {"status": "error", "message": "Không thể kết nối đến Web dịch vụ."}

def api_get_otp(order_id):
    """Khung hàm lấy mã OTP từ đơn hàng trên Web dịch vụ"""
    url = f"{DB_CONFIG['web_url']}/api/mail/otp"
    headers = {"Authorization": f"Bearer {DB_CONFIG['api_key']}"}
    params = {"order_id": order_id}
    try:
        # Trong thực tế:
        # response = requests.get(url, headers=headers, params=params, timeout=10)
        # return response.json()
        
        return {
            "status": "success",
            "otp": "".join(random.choices(string.digits, k=6)),
            "content": f"Ma xac minh cua ban la: {random.randint(10000,99999)}"
        }
    except Exception as e:
        print(f"Lỗi API Get OTP: {e}")
        return {"status": "error", "otp": None}

# ==========================================
# XÂY DỰNG GIAO DIỆN INLINE KEYBOARD ĐẸP MẮT
# ==========================================
def get_main_menu_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("📧 Thuê Mail", callback_data="user_rent_mail"),
        InlineKeyboardButton("💳 Nạp Tiền", callback_data="user_deposit"),
        InlineKeyboardButton("👤 Tài Khoản", callback_data="user_profile"),
        InlineKeyboardButton("📞 Liên Hệ", callback_data="user_contact")
    )
    return markup

def get_back_btn(callback_target="back_to_main"):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data=callback_target))
    return markup

def get_admin_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Thêm Admin Mới", callback_data="adm_add"),
        InlineKeyboardButton("📋 Danh Sách Admin", callback_data="adm_list"),
        InlineKeyboardButton("🖼️ Đổi Avatar Bot", callback_data="adm_avatar"),
        InlineKeyboardButton("🏦 Đổi Cấu Hình Bank", callback_data="adm_bank"),
        InlineKeyboardButton("⚙️ Cấu Hình Khác", callback_data="adm_config"),
        InlineKeyboardButton("📢 Gửi Thông Báo", callback_data="adm_broadcast"),
        InlineKeyboardButton("📊 Xem Doanh Thu", callback_data="adm_revenue"),
        InlineKeyboardButton("👥 Xem User Hôm Nay", callback_data="adm_users_today"),
        InlineKeyboardButton("🎁 Quản Lý Giftcode", callback_data="adm_giftcode"),
        InlineKeyboardButton("🔍 Quản Lý User", callback_data="adm_manage_users")
    )
    return markup

def get_admin_user_management_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 Cộng Tiền", callback_data="usrmng_add_money"),
        InlineKeyboardButton("📉 Trừ Tiền", callback_data="usrmng_sub_money"),
        InlineKeyboardButton("🚫 Ban User", callback_data="usrmng_ban"),
        InlineKeyboardButton("🔓 Unban User", callback_data="usrmng_unban"),
        InlineKeyboardButton("📜 Danh Sách Ban", callback_data="usrmng_ban_list"),
        InlineKeyboardButton("⬅️ Quay Lại Admin", callback_data="back_to_admin")
    )
    return markup

# ==========================================
# THAO TÁC CỦA NGƯỜI DÙNG (USER HANDLERS)
# ==========================================
@bot.message_handler(commands=['start'])
def command_start(message):
    try:
        uid = message.from_user.id
        is_ban, expiry, reason = check_ban_status(uid)
        if is_ban:
            bot.reply_to(message, f"⚠️ **TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA TRÊN HỆ THỐNG!**\n\n"
                                  f"🛑 **Lý do:** {reason}\n"
                                  f"⏳ **Thời gian mở khóa:** {expiry}\n\n"
                                  f"🤝 Vui lòng liên hệ Admin nếu có nhầm lẫn.", parse_mode="Markdown")
            return

        init_user_if_not_exists(message.from_user)
        
        welcome_caption = (
            f"⚡ **{DB_CONFIG['brand_name']}**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👋 Chào mừng **{message.from_user.first_name}** đến với hệ thống.\n"
            f"📌 __{DB_CONFIG['welcome_text']}__\n\n"
            f"💸 **Giá thuê mặc định:** `{DB_CONFIG['price_per_day']:,} VND` / 24 Giờ.\n"
            f"🏢 Đơn vị vận hành: **{DB_CONFIG['group_name']}**"
        )
        
        bot.send_photo(
            chat_id=message.chat.id,
            photo=DB_CONFIG["banner_url"],
            caption=welcome_caption,
            reply_markup=get_main_menu_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Lỗi lệnh /start: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('user_') or call.data == 'back_to_main')
def handle_user_callbacks(call):
    try:
        uid = call.from_user.id
        is_ban, expiry, reason = check_ban_status(uid)
        if is_ban:
            bot.answer_callback_query(call.id, "Tài khoản của bạn đang bị khóa!", show_alert=True)
            return

        init_user_if_not_exists(call.from_user)

        if call.data == "back_to_main":
            welcome_caption = (
                f"⚡ **{DB_CONFIG['brand_name']}**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👋 Chào mừng **{call.from_user.first_name}** trở lại.\n"
                f"📌 __{DB_CONFIG['welcome_text']}__\n\n"
                f"💸 **Giá thuê:** `{DB_CONFIG['price_per_day']:,} VND` / 24h."
            )
            bot.edit_message_media(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["banner_url"], caption=welcome_caption, parse_mode="Markdown"),
                reply_markup=get_main_menu_keyboard()
            )

        elif call.data == "user_profile":
            u_data = DB_USERS[uid]
            active_mails = sum(1 for m in u_data["history"] if m.get("status") == "active")
            
            profile_text = (
                f"👤 **THÔNG TIN TÀI KHOẢN NGƯỜI DÙNG**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🆔 **ID Telegram:** `{uid}`\n"
                f"🏷️ **Username:** @{u_data['username']}\n"
                f"💰 **Số dư hiện tại:** `{u_data['balance']:,} VND`\n"
                f"💳 **Tổng nạp tích lũy:** `{u_data['total_deposit']:,} VND`\n"
                f"📧 **Mail đang thuê:** `{active_mails} Mail`\n\n"
                f"📜 **Lịch sử giao dịch gần nhất:**\n"
            )
            if not u_data["history"]:
                profile_text += "👉 _Chưa có lịch sử thuê mail nào._"
            else:
                for idx, item in enumerate(u_data["history"][-5:], 1):
                    profile_text += f" {idx}. `{item['mail']}` | OTP: *{item['otp']}* ({item['app']})\n"

            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📜 Xem Chi Tiết Lịch Sử Thuê", callback_data="user_view_history"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="back_to_main"))

            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=profile_text,
                reply_markup=markup,
                parse_mode="Markdown"
            )

        elif call.data == "user_view_history":
            u_data = DB_USERS[uid]
            history_text = "📜 **LỊCH SỬ THUÊ MAIL TOÀN BỘ SYSTEM**\n━━━━━━━━━━━━━━━━━━\n"
            if not u_data["history"]:
                history_text += "🔔 Bạn chưa từng thuê Mail trên hệ thống."
            else:
                for idx, item in enumerate(u_data["history"], 1):
                    history_text += f"🔹 `{idx}`. **Mail:** `{item['mail']}`\n      🏷️ Ứng dụng: {item['app']} | 🔑 OTP: `{item['otp']}`\n"
            
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=history_text,
                reply_markup=get_back_btn("user_profile"),
                parse_mode="Markdown"
            )

        elif call.data == "user_contact":
            contact_text = (
                f"📞 **THÔNG TIN LIÊN HỆ & HỖ TRỢ CHĂM SÓC KHÁCH HÀNG**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"🛡️ **Hệ thống thuộc:** {DB_CONFIG['group_name']}\n"
                f"🌐 **Website:** [{DB_CONFIG['web_url']}]({DB_CONFIG['web_url']})\n"
                f"👑 **Admin:** {DB_CONFIG['admin_contact']}\n"
                f"⚡ **Support Kỹ Thuật:** {DB_CONFIG['support_contact']}\n\n"
                f"🔔 Đội ngũ hỗ trợ túc trực từ 8:00 đến 23:00 hàng ngày."
            )
            bot.edit_message_caption(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                caption=contact_text,
                reply_markup=get_back_btn(),
                parse_mode="Markdown",
                disable_web_page_preview=True
            )

        elif call.data == "user_deposit":
            dep_code = generate_deposit_code(DB_USERS[uid]["username"])
            dep_text = (
                f"🏦 **THÔNG TIN CHUYỂN KHOẢN NẠP TIỀN**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"📌 Vui lòng chuyển tiền đúng thông tin bên dưới:\n\n"
                f"🏛️ **Ngân hàng:** `{DB_CONFIG['bank_name']}`\n"
                f"💳 **Số Tài Khoản:** `{DB_CONFIG['bank_account']}`\n"
                f"👤 **Chủ Tài Khoản:** `{DB_CONFIG['bank_holder']}`\n"
                f"📝 **Nội dung bắt buộc:** `{dep_code}`\n\n"
                f"🛑 **Mức nạp tối thiểu (Min):** `{DB_CONFIG['min_deposit']:,} VND`\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ **CẢNH BÁO:** Nghiêm cấm gửi bill giả mạo/chỉnh sửa. Hệ thống tự động quét dữ liệu ngân hàng, nếu phát hiện gian lận sẽ ngay lập tức **KHÓA TÀI KHOẢN** vĩnh viễn và đóng băng số dư."
            )
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📸 Gửi Bill Xác Nhận", callback_data=f"user_send_bill_{dep_code}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data="back_to_main"))
            
            bot.edit_message_media(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["bank_qr"], caption=dep_text, parse_mode="Markdown"),
                reply_markup=markup
            )

        elif call.data.startswith("user_send_bill_"):
            code = call.data.replace("user_send_bill_", "")
            msg = bot.send_message(call.message.chat.id, "📸 Vui lòng gửi **Ảnh chụp biên lai (Bill) chuyển khoản** thành công của bạn lên đây:")
            bot.register_next_step_handler(msg, process_user_bill_upload, code)

        elif call.data == "user_rent_mail":
            u_data = DB_USERS[uid]
            if u_data["balance"] < DB_CONFIG["price_per_day"]:
                bot.answer_callback_query(call.id, f"Số dư không đủ! Cần tối thiểu {DB_CONFIG['price_per_day']:,} VND", show_alert=True)
                return
            
            # Gọi API lấy mail giả định từ Tangtuongtacsieure.com
            api_res = api_get_mail_list()
            if api_res.get("status") == "success" and api_res.get("data"):
                chosen_mail_info = random.choice(api_res["data"])
                mail_addr = chosen_mail_info["mail"]
                app_name = chosen_mail_info["app"]
                
                # Trừ tiền user
                u_data["balance"] -= DB_CONFIG["price_per_day"]
                DB_REVENUE["rent_today"] += DB_CONFIG["price_per_day"]
                
                # Gọi API lấy mã OTP (Giả lập)
                otp_res = api_get_otp(order_id=random.randint(1000, 9999))
                otp_code = otp_res.get("otp") if otp_res.get("otp") else "CHƯA CÓ"
                
                # Lưu lịch sử
                history_item = {
                    "mail": mail_addr,
                    "app": app_name,
                    "otp": otp_code,
                    "status": "active",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                u_data["history"].append(history_item)
                
                rent_success_text = (
                    f"🎉 **THUÊ MAIL THÀNH CÔNG!**\n"
                    f"━━━━━━━━━━━━━━━━━━\n"
                    f"📧 **Email nhận được:** `{mail_addr}`\n"
                    f"📱 **Dịch vụ cấu hình:** `{app_name}`\n"
                    f"🔑 **Mã OTP/Kích hoạt:** `{otp_code}`\n"
                    f"⏳ **Thời gian thuê:** `24 Giờ`\n"
                    f"💸 **Số dư tài khoản còn:** `{u_data['balance']:,} VND`"
                )
                bot.edit_message_caption(
                    chat_id=call.message.chat.id,
                    message_id=call.message.message_id,
                    caption=rent_success_text,
                    reply_markup=get_back_btn(),
                    parse_mode="Markdown"
                )
            else:
                bot.answer_callback_query(call.id, "❌ Kho hàng trên Web hiện tại đang hết Mail. Vui lòng quay lại sau!", show_alert=True)

    except Exception as e:
        print(f"Lỗi Callback User: {e}")

def process_user_bill_upload(message, code):
    try:
        uid = message.from_user.id
        if not message.photo:
            bot.reply_to(message, "❌ Sai định dạng! Bạn phải gửi một **Bức Ảnh** hóa đơn. Vui lòng bấm nạp tiền và thực hiện lại.")
            return
        
        photo_id = message.photo[-1].file_id
        user_name = DB_USERS[uid]["username"]
        
        # Đẩy thông báo duyệt nạp về cho tất cả Admin
        admin_markup = InlineKeyboardMarkup()
        admin_markup.add(
            InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"admapp_approve_{uid}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"admapp_reject_{uid}")
        )
        
        admin_notif_text = (
            f"🔔 **CÓ ĐƠN NẠP TIỀN MỚI CẦN DUYỆT!**\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"👤 **Khách hàng:** @{user_name} (`{uid}`)\n"
            f"📝 **Mã nội dung hệ thống tạo:** `{code}`\n"
            f"🕒 **Thời gian gửi:** {datetime.now().strftime('%H:%M:%S')}\n"
            f"👇 Bấm nút bên dưới để xử lý đơn nạp này:"
        )
        
        for adm in ADMINS:
            try:
                bot.send_photo(chat_id=adm, photo=photo_id, caption=admin_notif_text, reply_markup=admin_markup, parse_mode="Markdown")
            except Exception:
                pass
                
        bot.reply_to(message, "✅ **Gửi Bill xác nhận thành công!** Hoá đơn đã được gửi tới Ban quản trị. Hệ thống sẽ cộng tiền ngay sau khi được phê duyệt.")
    except Exception as e:
        print(f"Lỗi xử lý upload bill: {e}")

# ==========================================
# HỆ THỐNG QUẢN LÝ CHO ADMIN (ADMIN MANAGEMENT)
# ==========================================
@bot.message_handler(commands=['admin'])
def command_admin(message):
    try:
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "🔴 Bạn không có quyền truy cập khu vực Admin.")
            return
        
        bot.send_message(
            chat_id=message.chat.id,
            text=f"👑 **HỆ THỐNG QUẢN TRỊ ĐỒNG QUYỀN BOT MAIL 24H**\n"
                 f"━━━━━━━━━━━━━━━━━━\n"
                 f"Chào Admin, mọi tác vụ điều khiển đều dùng Menu Nút dưới đây. Tuyệt đối không gõ chữ tùy tiện.",
            reply_markup=get_admin_keyboard(),
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Lỗi lệnh /admin: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('adm') or call.data.startswith('usrmng_') or call.data == 'back_to_admin')
def handle_admin_callbacks(call):
    try:
        uid = call.from_user.id
        if uid not in ADMINS:
            bot.answer_callback_query(call.id, "Từ chối quyền truy cập!", show_alert=True)
            return

        if call.data == "back_to_admin":
            bot.edit_message_text(
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                text=f"👑 **HỆ THỐNG QUẢN TRỊ ĐỒNG QUYỀN BOT MAIL 24H**\n━━━━━━━━━━━━━━━━━━\nChọn mục cấu hình:",
                reply_markup=get_admin_keyboard(),
                parse_mode="Markdown"
            )

        elif call.data == "adm_list":
            adm_text = "📋 **DANH SÁCH BAN QUẢN TRỊ ĐỒNG QUYỀN**\n━━━━━━━━━━━━━━━━━━\n"
            for index, adm_id in enumerate(ADMINS, 1):
                username_str = DB_USERS.get(adm_id, {}).get("username", "Chưa Cập Nhật")
                adm_text += f"{index}. ID: `{adm_id}` | `@ {username_str}`\n"
            bot.edit_message_text(adm_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "adm_add":
            msg = bot.send_message(call.message.chat.id, "➕ Nhập **UID Telegram** của Admin mới cần cấp quyền:")
            bot.register_next_step_handler(msg, process_add_admin)

        elif call.data == "adm_avatar":
            msg = bot.send_message(call.message.chat.id, "🖼️ Gửi link ảnh mới hoặc gửi **Trực Tiếp Một Bức Ảnh** để đổi Banner chính:")
            bot.register_next_step_handler(msg, process_change_avatar)

        elif call.data == "adm_bank":
            msg = bot.send_message(call.message.chat.id, "🏦 Nhập chuỗi cấu hình ngân hàng theo định dạng:\n`Tên Ngân Hàng|STK|Tên Chủ Khoản` \n_Ví dụ: Vietcombank|10234567|NGUYEN VAN A_")
            bot.register_next_step_handler(msg, process_change_bank)

        elif call.data == "adm_config":
            msg = bot.send_message(call.message.chat.id, "⚙️ Nhập giá trị cấu hình thay đổi theo định dạng:\n`Giá thuê gốc|Mức nạp min` \n_Ví dụ: 1200|20000_")
            bot.register_next_step_handler(msg, process_other_config)

        elif call.data == "adm_revenue":
            total_users = len(DB_USERS)
            rev_text = (
                f"📊 **BÁO CÁO DOANH THU & HỆ THỐNG**\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"👥 Tổng số thành viên: `{total_users} Users`\n"
                f"💳 Doanh số nạp tiền hôm nay: `{DB_REVENUE['deposit_today']:,} VND`\n"
                f"📧 Tiền thuê Mail thu hôm nay: `{DB_REVENUE['rent_today']:,} VND`\n"
                f"📈 Doanh thu ước tính Tuần/Tháng: Tự động lũy kế trên Web Partner."
            )
            bot.edit_message_text(rev_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "adm_users_today":
            num_today = len(DB_REVENUE["new_users_today"])
            bot.edit_message_text(f"👥 **Số lượng User tương tác mới hôm nay:** `{num_today} Users`", call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "adm_giftcode":
            msg = bot.send_message(call.message.chat.id, "🎁 Nhập định dạng tạo Code mới:\n`TÊNCODE|SỐ_TIỀN|SỐ_LƯỢT` \n_Ví dụ: KM50K|50000|10_")
            bot.register_next_step_handler(msg, process_create_giftcode)

        elif call.data == "adm_broadcast":
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🌍 Toàn Bộ Hệ Thống", callback_data="admbroad_all"),
                       InlineKeyboardButton("👤 Riêng Lẻ (1 User)", callback_data="admbroad_one"))
            bot.edit_message_text("📢 Chọn chế độ phát thông báo:", call.message.chat.id, call.message.message_id, reply_markup=markup)

        elif call.data == "adm_manage_users":
            bot.edit_message_text("🔍 **KHU VỰC QUẢN TRỊ TÀI KHOẢN KHÁCH HÀNG**", call.message.chat.id, call.message.message_id, reply_markup=get_admin_user_management_keyboard())

        # Sub-menu Quản lý User
        elif call.data == "usrmng_add_money":
            msg = bot.send_message(call.message.chat.id, "💵 Nhập thông tin: `UID|Số_Tiền` để CỘNG tiền:")
            bot.register_next_step_handler(msg, process_usrmng_balance, "add")
        elif call.data == "usrmng_sub_money":
            msg = bot.send_message(call.message.chat.id, "📉 Nhập thông tin: `UID|Số_Tiền` để TRỪ tiền:")
            bot.register_next_step_handler(msg, process_usrmng_balance, "sub")
        elif call.data == "usrmng_ban":
            msg = bot.send_message(call.message.chat.id, "🚫 Nhập thông tin: `UID|Lý do ban`:")
            bot.register_next_step_handler(msg, process_usrmng_ban_step1)
        elif call.data == "usrmng_unban":
            msg = bot.send_message(call.message.chat.id, "🔓 Nhập UID khách hàng muốn mở khóa (Unban):")
            bot.register_next_step_handler(msg, process_usrmng_unban)
        elif call.data == "usrmng_ban_list":
            ban_text = "📜 **DANH SÁCH USER ĐANG BỊ CẤM TRUY CẬP**\n━━━━━━━━━━━━━━━━━━\n"
            if not DB_BAN_LIST:
                ban_text += "👉 Hiện tại không có user nào bị khóa."
            else:
                for b_uid, b_info in DB_BAN_LIST.items():
                    ban_text += f"🔹 **UID:** `{b_uid}`\n      🛑 Lý do: {b_info['reason']}\n      ⏳ Hạn mở: `{b_info['expiry']}`\n"
            bot.edit_message_text(ban_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("adm_manage_users"), parse_mode="Markdown")

    except Exception as e:
        print(f"Lỗi Admin Callback: {e}")

# ==========================================
# CÁC HÀM XỬ LÝ NEXT STEP CHO ADMIN
# ==========================================
def process_add_admin(message):
    try:
        new_uid = int(message.text.strip())
        if new_uid not in ADMINS:
            ADMINS.append(new_uid)
            bot.reply_to(message, f"✅ Đã thêm UID `{new_uid}` làm Quản trị viên đồng quyền thành công!", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ UID này đã là Admin từ trước.")
    except Exception:
        bot.reply_to(message, "❌ Vui lòng chỉ nhập chuỗi ký tự số (UID số). Thao tác thất bại.")

def process_change_avatar(message):
    try:
        if message.photo:
            file_id = message.photo[-1].file_id
            file_info = bot.get_file(file_id)
            url = f"https://api.telegram.org/file/bot{API_TOKEN}/{file_info.file_path}"
            DB_CONFIG["banner_url"] = url
        else:
            DB_CONFIG["banner_url"] = message.text.strip()
        bot.reply_to(message, "✅ Đã thay đổi Banner đại diện của Bot thành công!")
    except Exception as e:
        bot.reply_to(message, f"❌ Lỗi cấu hình ảnh: {e}")

def process_change_bank(message):
    try:
        parts = message.text.split("|")
        DB_CONFIG["bank_name"] = parts[0].strip()
        DB_CONFIG["bank_account"] = parts[1].strip()
        DB_CONFIG["bank_holder"] = parts[2].strip()
        # Tạo lại mã QR tự động bằng API VietQR
        DB_CONFIG["bank_qr"] = f"https://api.vietqr.io/image/970422-{parts[1].strip()}-YL66FmK.jpg"
        bot.reply_to(message, "✅ Cập nhật cấu hình thông tin ngân hàng thành công!")
    except Exception:
        bot.reply_to(message, "❌ Định dạng sai. Vui lòng nhập đúng mẫu: Tên Ngân Hàng|STK|Tên Chủ Khoản")

def process_other_config(message):
    try:
        parts = message.text.split("|")
        DB_CONFIG["price_per_day"] = int(parts[0].strip())
        DB_CONFIG["min_deposit"] = int(parts[1].strip())
        bot.reply_to(message, "✅ Đã lưu cấu hình mới.")
    except Exception:
        bot.reply_to(message, "❌ Sai định dạng số nguyên. Cấu hình thất bại.")

def process_create_giftcode(message):
    try:
        code, amount, count = message.text.split("|")
        DB_GIFTCODES[code.strip()] = {
            "amount": int(amount.strip()),
            "count": int(count.strip()),
            "used_by": []
        }
        bot.reply_to(message, f"✅ Đã tạo Giftcode: `{code.strip()}` nhận `{int(amount):,}` VND cho `{count}` người dùng.", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Thất bại. Vui lòng nhập đúng: CODE|SỐ_TIỀN|SỐ_LƯỢT")

def process_usrmng_balance(message, action_type):
    try:
        uid, amt = message.text.split("|")
        uid = int(uid.strip())
        amt = int(amt.strip())
        
        if uid not in DB_USERS:
            bot.reply_to(message, "❌ Thành viên này chưa từng nhấn /start bot nên không thể thay đổi số dư.")
            return
            
        if action_type == "add":
            DB_USERS[uid]["balance"] += amt
            DB_USERS[uid]["total_deposit"] += amt
            bot.reply_to(message, f"✅ Đã cộng `{amt:,} VND` cho User `{uid}`.", parse_mode="Markdown")
            bot.send_message(uid, f"🔔 **Thông báo:** Tài khoản của bạn được cộng `{amt:,} VND` từ Ban quản trị.", parse_mode="Markdown")
        else:
            DB_USERS[uid]["balance"] = max(0, DB_USERS[uid]["balance"] - amt)
            bot.reply_to(message, f"✅ Đã trừ `{amt:,} VND` của User `{uid}`.", parse_mode="Markdown")
            bot.send_message(uid, f"🔔 **Thông báo:** Tài khoản của bạn bị khấu trừ `{amt:,} VND` từ Ban quản trị.", parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Sai cấu trúc nhập dữ liệu. Mẫu đúng: UID|SỐ_TIỀN")

def process_usrmng_ban_step1(message):
    try:
        uid_str, reason = message.text.split("|")
        uid = int(uid_str.strip())
        
        markup = InlineKeyboardMarkup()
        markup.add(
            InlineKeyboardButton("1 Ngày", callback_data=f"admban_1_{uid}_{reason}"),
            InlineKeyboardButton("7 Ngày", callback_data=f"admban_7_{uid}_{reason}"),
            InlineKeyboardButton("30 Ngày", callback_data=f"admban_30_{uid}_{reason}"),
            InlineKeyboardButton("Vĩnh Viễn", callback_data=f"admban_0_{uid}_{reason}")
        )
        bot.send_message(message.chat.id, f"Chọn thời gian khóa cho User `{uid}`:", reply_markup=markup, parse_mode="Markdown")
    except Exception:
        bot.reply_to(message, "❌ Lỗi định dạng! Mẫu chuẩn: UID|Lý do")

def process_usrmng_unban(message):
    try:
        uid = int(message.text.strip())
        if uid in DB_BAN_LIST:
            del DB_BAN_LIST[uid]
            bot.reply_to(message, f"🔓 Đã mở khóa (Unban) thành công cho tài khoản `{uid}`.", parse_mode="Markdown")
            bot.send_message(uid, "🔔 **Chúc mừng:** Tài khoản của bạn đã được Admin mở khóa trên hệ thống. Hãy gõ /start để tiếp tục.")
        else:
            bot.reply_to(message, "❌ UID này không có trong danh sách đen.")
    except Exception:
        bot.reply_to(message, "❌ Chỉ nhập chữ số UID.")

# ==========================================
# PHÁT SÓNG TIN NHẮN (BROADCAST HANDLERS)
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('admbroad_'))
def handle_broadcast_selection(call):
    mode = call.data.replace("admbroad_", "")
    msg = bot.send_message(call.message.chat.id, "❓ Bạn có muốn đính kèm Tệp Phương Tiện (Ảnh/Video) không? Nhập `Có` hoặc `Không`:")
    bot.register_next_step_handler(msg, process_broadcast_media_step, mode)

def process_broadcast_media_step(message, mode):
    has_media = message.text.strip().lower() in ["có", "co", "yes"]
    if mode == "all":
        msg = bot.send_message(message.chat.id, "✍️ Vui lòng gửi nội dung thông báo phát đi (Gửi kèm ảnh/video nếu vừa chọn Có):")
        bot.register_next_step_handler(msg, send_broadcast_final, None, has_media)
    else:
        msg = bot.send_message(message.chat.id, "👤 Vui lòng nhập UID của người nhận:")
        bot.register_next_step_handler(msg, process_broadcast_target_one, has_media)

def process_broadcast_target_one(message, has_media):
    try:
        target_uid = int(message.text.strip())
        msg = bot.send_message(message.chat.id, f"✍️ Nhập nội dung gửi cho User `{target_uid}`:")
        bot.register_next_step_handler(msg, send_broadcast_final, target_uid, has_media)
    except Exception:
        bot.reply_to(message, "❌ Thất bại. UID phải là một dãy số.")

def send_broadcast_final(message, target_uid, has_media):
    try:
        targets = [target_uid] if target_uid else list(DB_USERS.keys())
        count = 0
        
        for u in targets:
            try:
                if has_media:
                    if message.photo:
                        bot.send_photo(u, message.photo[-1].file_id, caption=message.caption, parse_mode="Markdown")
                    elif message.video:
                        bot.send_video(u, message.video.file_id, caption=message.caption, parse_mode="Markdown")
                else:
                    bot.send_message(u, message.text, parse_mode="Markdown")
                count += 1
            except Exception:
                pass
                
        bot.reply_to(message, f"📢 Đã phát tín hiệu gửi thành công tới `{count}` tài khoản nhận tin nhắn.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"❌ Không thể phát sóng tin nhắn do: {e}")

# ==========================================
# XỬ LÝ DUYỆT NẠP TIỀN HOẶC BAN USER QUA INLINE
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('admapp_') or call.data.startswith('admban_'))
def handle_admin_actions(call):
    try:
        if call.from_user.id not in ADMINS:
            return

        if call.data.startswith("admapp_approve_"):
            target_uid = int(call.data.replace("admapp_approve_", ""))
            msg = bot.send_message(call.message.chat.id, f"💰 Nhập số tiền cần cộng cho tài khoản `{target_uid}`:")
            bot.register_next_step_handler(msg, final_approve_deposit, target_uid, call.message)

        elif call.data.startswith("admapp_reject_"):
            target_uid = int(call.data.replace("admapp_reject_", ""))
            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton("Bill mờ/Không thấy nội dung", callback_data=f"admrejreason_mo_{target_uid}"),
                InlineKeyboardButton("Sai nội dung chuyển khoản", callback_data=f"admrejreason_sai_{target_uid}"),
                InlineKeyboardButton("Hình ảnh bill fake/chỉnh sửa", callback_data=f"admrejreason_fake_{target_uid}")
            )
            bot.send_message(call.message.chat.id, "❌ Chọn lý do từ chối nạp:", reply_markup=markup)

        elif call.data.startswith("admban_"):
            # Format: admban_days_uid_reason
            _, days, target_uid, reason = call.data.split("_", 3)
            target_uid = int(target_uid)
            days = int(days)
            
            if days == 0:
                expiry_str = "Vĩnh Viễn"
            else:
                expiry_str = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
                
            DB_BAN_LIST[target_uid] = {"reason": reason, "expiry": expiry_str}
            bot.edit_message_text(f"🛑 Đã thực hiện khóa tài khoản `{target_uid}` với thời hạn: `{expiry_str}`", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
            
            try:
                bot.send_message(target_uid, f"⚠️ Tài khoản của bạn đã bị Admin khóa.\n🛑 Lý do: {reason}\n⏳ Hết hạn: {expiry_str}")
            except Exception:
                pass

    except Exception as e:
        print(f"Lỗi Callback Phê Duyệt Tác vụ: {e}")

def final_approve_deposit(message, target_uid, orig_admin_msg):
    try:
        amount = int(message.text.strip())
        if target_uid in DB_USERS:
            DB_USERS[target_uid]["balance"] += amount
            DB_USERS[target_uid]["total_deposit"] += amount
            DB_REVENUE["deposit_today"] += amount
            
            bot.send_message(target_uid, f"🎉 **THÔNG BÁO NẠP TIỀN THÀNH CÔNG!**\n━━━━━━━━━━━━━━━━━━\n💳 Bạn đã được phê duyệt số tiền: `+{amount:,} VND`.\n💰 Số dư hiện tại: `{DB_USERS[target_uid]['balance']:,} VND`.", parse_mode="Markdown")
            bot.edit_message_caption("✅ ĐÃ DUYỆT CỘNG TIỀN THÀNH CÔNG!", orig_admin_msg.chat.id, orig_admin_msg.message_id)
        else:
            bot.reply_to(message, "❌ Thất bại. Thành viên này không có dữ liệu trên Bot.")
    except Exception:
        bot.reply_to(message, "❌ Sai số lượng tiền tệ nhập vào.")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admrejreason_'))
def final_reject_reason(call):
    try:
        _, reason_code, target_uid = call.data.split("_")
        target_uid = int(target_uid)
        
        reason_map = {
            "mo": "Hình ảnh hóa đơn bị mờ, không rõ thông tin giao dịch.",
            "sai": "Chuyển khoản sai nội dung cấu trúc được yêu cầu.",
            "fake": "Hệ thống phát hiện hình ảnh biên lai giả mạo/chỉnh sửa."
        }
        reason_str = reason_map.get(reason_code, "Không đúng điều khoản giao dịch.")
        
        bot.send_message(target_uid, f"❌ **ĐƠN NẠP TIỀN CỦA BẠN BỊ TỪ CHỐI!**\n━━━━━━━━━━━━━━━━━━\n🛑 **Lý do:** {reason_str}\n💬 Vui lòng kiểm tra lại thông tin hoặc liên hệ Hỗ trợ khách hàng.", parse_mode="Markdown")
        bot.edit_message_text(f"❌ Đã từ chối đơn nạp của User `{target_uid}` với lý do: {reason_str}", call.message.chat.id, call.message.message_id, parse_mode="Markdown")
    except Exception as e:
        print(f"Lỗi reject: {e}")

# ==========================================
# KIẾN TRÚC WEBHOOK FLASK VÀ KHỞI CHẠY HỆ THỐNG
# ==========================================
@app.route('/', methods=['GET', 'HEAD'])
def index():
    return "Hệ thống Bot Mail 24H đang vận hành trực tuyến 24/7!", 200

@app.route(f'/{API_TOKEN}/', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    else:
        return 'Forbidden', 403

if __name__ == '__main__':
    # Xoá Webhook cũ và thiết lập Webhook mới đồng bộ
    bot.remove_webhook()
    time.sleep(0.5)
    bot.set_webhook(url=WEBHOOK_URL)
    print(f"🚀 Bot đang lắng nghe tại Webhook URL: {WEBHOOK_URL}")
    
    # Khởi chạy Flask app để bắt và điều hướng cổng PORT trên Render.com
    app.run(host='0.0.0.0', port=PORT)
