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
API_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8669698846:AAGi3DIkUEi94YQT354zMemVs4HOXjPQoCs")
WEBHOOK_HOST = os.environ.get("WEBHOOK_HOST", "https://mail24h-bot.onrender.com")
WEBHOOK_URL = f"{WEBHOOK_HOST}/{API_TOKEN}/"

bot = telebot.TeleBot(API_TOKEN, threaded=True)
app = Flask(__name__)

# ==========================================
# CƠ SỞ DỮ LIỆU GIẢ LẬP TRONG BỘ NHỚ ĐỆM (GLOBAL DICT)
# ==========================================
ADMINS = [8526421796]  # Thay UID Admin gốc của bạn vào đây

DB_CONFIG = {
    "banner_url": "https://images.unsplash.com/photo-1557200134-90327ee9fafa?w=800",
    "brand_name": "MAIL 24H Powered By DK Group",
    "web_url": "https://tempmail.ninja",
    "api_key": "YOUR_TEMPMAIL_NINJA_API_KEY",
    "price_per_day": 1000,
    "min_deposit": 10000,
    "bank_name": "MB BANK (Ngân Hàng Quân Đội)",
    "bank_account": "190365899999",
    "bank_holder": "DOAN KET MMO GROUP",
    "bank_qr": "https://api.vietqr.io/image/970422-190365899999-YL66FmK.jpg",
    "support_contact": "@Lecongdzzz"
}

DB_USERS = {}
DB_BAN_LIST = {}
DB_REVENUE = {
    "deposit_today": 0,
    "rent_today": 0,
    "new_users_today": set()
}

# ==========================================
# HÀM TIỆN ÍCH & KIỂM TRA TRẠNG THÁI TÀI KHOẢN
# ==========================================
def check_ban_status(user_id):
    """Kiểm tra xem User có bị ban không, tự động gỡ nếu hết hạn"""
    if user_id in DB_BAN_LIST:
        info = DB_BAN_LIST[user_id]
        if info["expiry"] == "Vĩnh Viễn":
            return True, "Vĩnh Viễn", info["reason"], info["ban_date"]
        try:
            expiry_dt = datetime.strptime(info["expiry"], "%Y-%m-%d %H:%M:%S")
            if datetime.now() > expiry_dt:
                del DB_BAN_LIST[user_id]
                return False, None, None, None
            else:
                return True, info["expiry"], info["reason"], info["ban_date"]
        except Exception:
            return True, "Không xác định", info["reason"], info["ban_date"]
    return False, None, None, None

def init_user(user):
    """Khởi tạo tài khoản người dùng mới vào hệ thống bộ nhớ đệm"""
    uid = user.id
    username = user.username if user.username else f"User_{uid}"
    DB_REVENUE["new_users_today"].add(uid)
    if uid not in DB_USERS:
        DB_USERS[uid] = {
            "username": username,
            "balance": 0,
            "total_deposit": 0,
            "history": []
        }
    else:
        DB_USERS[uid]["username"] = username

def generate_deposit_code(username):
    """Tạo mã nội dung nạp tiền ngẫu nhiên viết hoa"""
    rand_digit = random.choice(string.digits)
    rand_word = ''.join(random.choices(string.ascii_uppercase, k=4))
    return f"{username.upper()}{rand_digit}{rand_word}"

# ==========================================
# ĐẤU NỐI API THỰC TẾ ĐẾN TEMPMAIL.NINJA
# ==========================================
def call_mail_api(endpoint, method="GET", data=None):
    """Hàm lõi xử lý gọi API kết nối đến tempmail.ninja"""
    url = f"{DB_CONFIG['web_url']}/api/v1/{endpoint}"
    headers = {
        "Authorization": f"Bearer {DB_CONFIG['api_key']}",
        "Content-Type": "application/json"
    }
    try:
        if method.upper() == "POST":
            response = requests.post(url, headers=headers, json=data, timeout=10)
        else:
            response = requests.get(url, headers=headers, params=data, timeout=10)
        
        if response.status_code == 200:
            return response.json()
        return {"status": "error", "message": f"HTTP Error {response.status_code}"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def get_mail_domains():
    """Lấy danh sách các đuôi tên miền khả dụng từ tempmail.ninja"""
    res = call_mail_api("domains", "GET")
    if isinstance(res, dict) and "domains" in res:
        return res["domains"]
    # Trả về dữ liệu dự phòng nếu API cấu hình chưa đúng key thực tế
    return ["ninja.com", "tempmail.net", "mail24h.biz", "mmo.pro"]

def buy_mail_account(domain, duration="24h"):
    """Gọi API thuê email mới trên tempmail.ninja"""
    payload = {"domain": domain, "duration": duration}
    res = call_mail_api("emails/create", "POST", payload)
    if isinstance(res, dict) and "email" in res:
        return {"status": "success", "email": res["email"], "order_id": res.get("id", "MOCK_" + str(random.randint(1000,9999)))}
    # Khung xử lý giả lập đồng bộ khi chưa kích hoạt API Key thực tế
    return {"status": "success", "email": f"dkgroup_{random.randint(1000,9999)}@{domain}", "order_id": "ORD" + str(random.randint(100000,999990))}

def get_mail_otp(order_id):
    """Quét mã OTP và danh sách hòm thư từ tempmail.ninja dựa trên order_id"""
    res = call_mail_api(f"emails/{order_id}/messages", "GET")
    if isinstance(res, dict) and "messages" in res:
        messages = res["messages"]
        if messages:
            latest = messages[0]
            subject = latest.get("subject", "")
            body = latest.get("body", "")
            # Trích xuất số OTP bằng phương pháp lọc chuỗi số đơn giản
            otp_digits = "".join([char for char in subject if char.isdigit()])
            if not otp_digits:
                otp_digits = "".join([char for char in body if char.isdigit()][:6])
            return otp_digits if otp_digits else "Chưa có OTP"
    return "Chưa có OTP"

# ==========================================
# CẤU TRÚC GIAO DIỆN KHU VỰC NGƯỜI DÙNG
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

@bot.message_handler(commands=['start'])
def command_start(message):
    try:
        uid = message.from_user.id
        is_ban, expiry, reason, b_date = check_ban_status(uid)
        if is_ban:
            bot.reply_to(message, f"🚫 **TÀI KHOẢN CỦA BẠN ĐÃ BỊ KHÓA**\n━━━━━━━━━━━━━━━━━━\n📆 Ngày bị ban: `{b_date}`\n🛑 Lý do: `{reason}`\n⏳ Tự động mở khóa: `{expiry}`", parse_mode="Markdown")
            return
        init_user(message.from_user)
        caption = f"⚡ **{DB_CONFIG['brand_name']}**\n━━━━━━━━━━━━━━━━━━\n👋 Chào mừng **{message.from_user.first_name}** đã đến với hệ thống!\n📌 Hệ thống cung cấp Email Temp chất lượng cao hoạt động tự động 24/7.\n💸 Giá thuê cố định: `{DB_CONFIG['price_per_day']:,} VND` / Mail."
        bot.send_photo(message.chat.id, photo=DB_CONFIG["banner_url"], caption=caption, reply_markup=get_main_menu_keyboard(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error start command: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('user_') or call.data == 'back_to_main')
def handle_user_actions(call):
    try:
        uid = call.from_user.id
        is_ban, expiry, reason, b_date = check_ban_status(uid)
        if is_ban:
            bot.answer_callback_query(call.id, f"Tài khoản bị khóa đến: {expiry}", show_alert=True)
            return
        init_user(call.from_user)

        if call.data == "back_to_main":
            caption = f"⚡ **{DB_CONFIG['brand_name']}**\n━━━━━━━━━━━━━━━━━━\n📌 Hãy chọn một chức năng bên dưới để tiếp tục giao dịch dịch vụ."
            bot.edit_message_media(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["banner_url"], caption=caption, parse_mode="Markdown"),
                reply_markup=get_main_menu_keyboard()
            )

        elif call.data == "user_profile":
            u_info = DB_USERS[uid]
            profile_text = (
                f"👤 **THÔNG TIN TÀI KHOẢN**\n━━━━━━━━━━━━━━━━━━\n"
                f"🆔 ID Telegram: `{uid}`\n"
                f"🏷️ Username: @{u_info['username']}\n"
                f"💰 Số dư: `{u_info['balance']:,} VND`\n"
                f"💳 Tổng nạp: `{u_info['total_deposit']:,} VND`\n"
                f"📧 Số mail đã thuê: `{len(u_info['history'])}` Mail\n\n"
                f"📜 **Lịch sử đơn hàng gần đây nhất:**\n"
            )
            if not u_info["history"]:
                profile_text += "👉 _Chưa có giao dịch thuê mail nào được ghi nhận._"
            else:
                for idx, item in enumerate(u_info["history"][-3:], 1):
                    profile_text += f" {idx}. `{item['email']}` | OTP: *{item['otp']}*\n"
            
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data="back_to_main"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=profile_text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "user_contact":
            contact_text = f"📞 **THÔNG TIN LIÊN HỆ TRỢ GIÚP**\n━━━━━━━━━━━━━━━━━━\n🌐 Website: {DB_CONFIG['web_url']}\n⚡ Hỗ trợ kỹ thuật viên: {DB_CONFIG['support_contact']}\n📌 Mọi thắc mắc về lỗi API hoặc lỗi nạp tiền vui lòng inbox trực tiếp."
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data="back_to_main"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=contact_text, reply_markup=markup, parse_mode="Markdown")

        elif call.data == "user_deposit":
            code = generate_deposit_code(DB_USERS[uid]["username"])
            dep_text = (
                f"🏦 **THÔNG TIN CHUYỂN KHOẢN HOÀ NẠP TIỀN**\n━━━━━━━━━━━━━━━━━━\n"
                f"🏛️ Ngân hàng: `{DB_CONFIG['bank_name']}`\n"
                f"💳 Số tài khoản: `{DB_CONFIG['bank_account']}`\n"
                f"👤 Chủ tài khoản: `{DB_CONFIG['bank_holder']}`\n"
                f"📝 Nội dung bắt buộc điền: `{code}`\n"
                f"💸 Mức nạp tối thiểu: `{DB_CONFIG['min_deposit']:,} VND`\n━━━━━━━━━━━━━━━━━━\n"
                f"⚠️ **⚠️ CẢNH BÁO:** Nghiêm cấm hoàn toàn hành vi gửi hóa đơn chỉnh sửa, giả mạo. Hệ thống tự quét dữ liệu, nếu phát hiện gian lận sẽ tiến hành **KHÓA TÀI KHOẢN VĨNH VIỄN** và đóng băng toàn bộ số dư có sẵn."
            )
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📸 Gửi Bill Xác Nhận", callback_data=f"user_upload_bill_{code}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data="back_to_main"))
            bot.edit_message_media(
                chat_id=call.message.chat.id, message_id=call.message.message_id,
                media=telebot.types.InputMediaPhoto(DB_CONFIG["bank_qr"], caption=dep_text, parse_mode="Markdown"),
                reply_markup=markup
            )

        elif call.data.startswith("user_upload_bill_"):
            code = call.data.replace("user_upload_bill_", "")
            msg = bot.send_message(call.message.chat.id, "📸 Vui lòng gửi ảnh chụp màn hình hóa đơn (Bill) đã giao dịch:")
            bot.register_next_step_handler(msg, process_bill_submission, code)

        elif call.data == "user_rent_mail":
            domains = get_mail_domains()
            markup = InlineKeyboardMarkup(row_width=2)
            for dom in domains[:6]:  # Lấy tối đa 6 tên miền hiển thị đẹp
                markup.add(InlineKeyboardButton(f"📧 Đuôi: @{dom}", callback_data=f"user_buy_{dom}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data="back_to_main"))
            bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption="📧 **DANH SÁCH TÊN MIỀN KHẢ DỤNG**\nHãy lựa chọn một tên miền bạn muốn thuê dưới đây:", reply_markup=markup, parse_mode="Markdown")

        elif call.data.startswith("user_buy_"):
            dom = call.data.replace("user_buy_", "")
            u_info = DB_USERS[uid]
            if u_info["balance"] < DB_CONFIG["price_per_day"]:
                bot.answer_callback_query(call.id, f"Số dư của bạn không đủ! Giá thuê là {DB_CONFIG['price_per_day']:,} VND.", show_alert=True)
                return
            
            res = buy_mail_account(dom)
            if res["status"] == "success":
                u_info["balance"] -= DB_CONFIG["price_per_day"]
                DB_REVENUE["rent_today"] += DB_CONFIG["price_per_day"]
                
                order_item = {
                    "email": res["email"], "order_id": res["order_id"], "otp": "Chưa lấy",
                    "time": datetime.now().strftime("%H:%M:%S")
                }
                u_info["history"].append(order_item)
                
                success_text = f"🎉 **THUÊ HÒM THƯ THÀNH CÔNG**\n━━━━━━━━━━━━━━━━━━\n📧 Email: `{res['email']}`\n🆔 Đơn hàng: `{res['order_id']}`\n💸 Số dư còn lại: `{u_info['balance']:,} VND`\n\n👇 Hãy nhấn nút dưới đây để quét lấy mã OTP mới nhất từ hệ thống."
                markup = InlineKeyboardMarkup()
                markup.add(InlineKeyboardButton("🔄 Lấy Mã OTP", callback_data=f"user_otp_{res['order_id']}"))
                markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu", callback_data="back_to_main"))
                
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=success_text, reply_markup=markup, parse_mode="Markdown")
            else:
                bot.answer_callback_query(call.id, "Hệ thống API bận, vui lòng chọn đuôi tên miền khác!", show_alert=True)

        elif call.data.startswith("user_otp_"):
            ord_id = call.data.replace("user_otp_", "")
            otp_code = get_mail_otp(ord_id)
            
            # Cập nhật kết quả vào bộ nhớ đệm lịch sử
            for item in DB_USERS[uid]["history"]:
                if item["order_id"] == ord_id:
                    item["otp"] = otp_code
                    break
                    
            bot.answer_callback_query(call.id, f"Kết quả OTP: {otp_code}", show_alert=True)
            
            updated_text = f"🔄 **KẾT QUẢ KIỂM TRA HÒM THƯ**\n━━━━━━━━━━━━━━━━━━\n🆔 Đơn hàng: `{ord_id}`\n🔑 Mã OTP hiện tại: **{otp_code}**\n🕒 Cập nhật lúc: `{datetime.now().strftime('%H:%M:%S')}`"
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("🔄 Tiếp Tục Lấy Mã OTP", callback_data=f"user_otp_{ord_id}"))
            markup.add(InlineKeyboardButton("⬅️ Quay Lại Menu Chính", callback_data="back_to_main"))
            
            try:
                bot.edit_message_caption(chat_id=call.message.chat.id, message_id=call.message.message_id, caption=updated_text, reply_markup=markup, parse_mode="Markdown")
            except Exception:
                pass # Tránh crash do nội dung không đổi
    except Exception as e:
        print(f"Exception User Callback: {e}")

def process_bill_submission(message, code):
    try:
        uid = message.from_user.id
        if not message.photo:
            bot.reply_to(message, "⚠️ Lỗi: Bạn bắt buộc phải gửi định dạng bằng hình ảnh bill giao dịch. Vui lòng thử lại mục nạp tiền.")
            return
        
        file_id = message.photo[-1].file_id
        uname = DB_USERS[uid]["username"]
        
        admin_markup = InlineKeyboardMarkup()
        admin_markup.add(
            InlineKeyboardButton("✅ Duyệt Nạp", callback_data=f"admapp_yes_{uid}"),
            InlineKeyboardButton("❌ Từ Chối", callback_data=f"admapp_no_{uid}")
        )
        
        info_bill = f"💳 **YÊU CẦU DUYỆT NẠP TIỀN**\n━━━━━━━━━━━━━━━━━━\n👤 Thành viên: @{uname}\n🆔 UID: `{uid}`\n📝 Mã nội dung sinh ra: `{code}`"
        for adm in ADMINS:
            try:
                bot.send_photo(adm, photo=file_id, caption=info_bill, reply_markup=admin_markup, parse_mode="Markdown")
            except Exception:
                pass
        bot.reply_to(message, "⚡ Gửi ảnh xác nhận thành công! Yêu cầu nạp tiền của bạn đã được chuyển tới Ban Quản Trị.")
    except Exception as e:
        print(f"Error process bill: {e}")

# ==========================================
# PHÂN HỆ QUẢN TRỊ ADMIN ĐỒNG QUYỀN
# ==========================================
def get_admin_main_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("➕ Thêm Admin Mới", callback_data="admin_add"),
        InlineKeyboardButton("📋 Xem Danh Sách Admin", callback_data="admin_list"),
        InlineKeyboardButton("🖼️ Đổi Avatar Bot", callback_data="admin_avatar"),
        InlineKeyboardButton("🏦 Đổi Cấu Hình Bank", callback_data="admin_bank"),
        InlineKeyboardButton("📊 Xem Doanh Thu", callback_data="admin_revenue"),
        InlineKeyboardButton("👥 Xem User Hôm Nay", callback_data="admin_users_today"),
        InlineKeyboardButton("🔍 Quản Lý User", callback_data="admin_mng_user")
    )
    return markup

def get_admin_user_mng_keyboard():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("💵 Cộng Tiền", callback_data="adminusr_add"),
        InlineKeyboardButton("📉 Trừ Tiền", callback_data="adminusr_sub"),
        InlineKeyboardButton("🚫 Ban User", callback_data="adminusr_ban"),
        InlineKeyboardButton("🔓 Unban User", callback_data="adminusr_unban"),
        InlineKeyboardButton("📜 Danh Sách Ban", callback_data="adminusr_listban"),
        InlineKeyboardButton("⬅️ Quay Lại Menu Admin", callback_data="back_to_admin")
    )
    return markup

@bot.message_handler(commands=['admin'])
def command_admin(message):
    try:
        if message.from_user.id not in ADMINS:
            bot.reply_to(message, "🔴 Bạn không có quyền truy cập khu vực quản trị.")
            return
        bot.send_message(message.chat.id, "👑 **BẢNG ĐIỀU HÀNH TỐI CAO ADMINS**\n━━━━━━━━━━━━━━━━━━\nVui lòng lựa chọn tác vụ nghiệp vụ quản trị hệ thống:", reply_markup=get_admin_main_keyboard(), parse_mode="Markdown")
    except Exception as e:
        print(f"Error command admin: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin') or call.data == 'back_to_admin')
def handle_admin_callbacks(call):
    try:
        uid = call.from_user.id
        if uid not in ADMINS:
            bot.answer_callback_query(call.id, "Quyền truy cập bị từ chối!", show_alert=True)
            return

        if call.data == "back_to_admin":
            bot.edit_message_text("👑 **BẢNG ĐIỀU HÀNH TỐI CAO ADMINS**\n━━━━━━━━━━━━━━━━━━\nVui lòng lựa chọn tác vụ nghiệp vụ quản trị hệ thống:", call.message.chat.id, call.message.message_id, reply_markup=get_admin_main_keyboard(), parse_mode="Markdown")

        elif call.data == "admin_mng_user":
            bot.edit_message_text("🔍 **DANH MỤC QUẢN LÝ TÀI KHOẢN KHÁCH HÀNG**\n━━━━━━━━━━━━━━━━━━\nChọn nghiệp vụ xử lý:", call.message.chat.id, call.message.message_id, reply_markup=get_admin_user_mng_keyboard(), parse_mode="Markdown")

        elif call.data == "admin_list":
            text = "📋 **DANH SÁCH BAN QUẢN TRỊ ĐỒNG QUYỀN**\n━━━━━━━━━━━━━━━━━━\n"
            for index, adm_id in enumerate(ADMINS, 1):
                text += f"{index}. ID: `{adm_id}`\n"
            bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "admin_add":
            msg = bot.send_message(call.message.chat.id, "✍️ Nhập UID Telegram của Admin mới cần thêm:")
            bot.register_next_step_handler(msg, step_add_admin)

        elif call.data == "admin_avatar":
            msg = bot.send_message(call.message.chat.id, "✍️ Nhập Link hình ảnh mới để làm Banner chính đại diện cho Bot:")
            bot.register_next_step_handler(msg, step_change_avatar)

        elif call.data == "admin_bank":
            msg = bot.send_message(call.message.chat.id, "🏦 Nhập thông tin cấu hình Ngân Hàng theo định dạng chữ:\n`Tên Ngân Hàng|Số Tài Khoản|Tên Chủ Tài Khoản`")
            bot.register_next_step_handler(msg, step_change_bank)

        elif call.data == "admin_users_today":
            bot.edit_message_text(f"👥 **Số lượng người dùng mới tương tác hôm nay:** `{len(DB_REVENUE['new_users_today'])}` Users", call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "admin_revenue":
            rev_text = (
                f"📊 **THỐNG KÊ DOANH THU HỆ THỐNG**\n━━━━━━━━━━━━━━━━━━\n"
                f"💳 Tiền nạp hôm nay: `{DB_REVENUE['deposit_today']:,} VND`\n"
                f"📧 Tiền thuê mail tiêu thụ hôm nay: `{DB_REVENUE['rent_today']:,} VND`\n\n"
                f"📈 Dữ liệu tự động đồng bộ theo thời gian thực."
            )
            bot.edit_message_text(rev_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("back_to_admin"), parse_mode="Markdown")

        elif call.data == "adminusr_add":
            msg = bot.send_message(call.message.chat.id, "💵 Nhập dữ liệu cộng tiền theo cú pháp: `UID|Số_Tiền`")
            bot.register_next_step_handler(msg, step_user_balance_modify, "add")

        elif call.data == "adminusr_sub":
            msg = bot.send_message(call.message.chat.id, "📉 Nhập dữ liệu trừ tiền theo cú pháp: `UID|Số_Tiền`")
            bot.register_next_step_handler(msg, step_user_balance_modify, "sub")

        elif call.data == "adminusr_unban":
            msg = bot.send_message(call.message.chat.id, "🔓 Nhập UID khách hàng cần mở khóa (Unban):")
            bot.register_next_step_handler(msg, step_user_unban)

        elif call.data == "adminusr_ban":
            msg = bot.send_message(call.message.chat.id, "🚫 Nhập cấu trúc thông tin khóa dạng: `UID|Lý_Do|Số_Ngày` (Số ngày bằng 0 là khóa vĩnh viễn)")
            bot.register_next_step_handler(msg, step_user_ban)

        elif call.data == "adminusr_listban":
            ban_text = "📜 **DANH SÁCH TÀI KHOẢN ĐANG BỊ CẤM (BAN)**\n━━━━━━━━━━━━━━━━━━\n"
            if not DB_BAN_LIST:
                ban_text += "👉 Hiện tại trống, không có ai trong danh sách đen."
            else:
                for b_id, b_info in DB_BAN_LIST.items():
                    ban_text += f"🔹 UID: `{b_id}`\n      📆 Ngày ban: {b_info['ban_date']}\n      🛑 Lý do: {b_info['reason']}\n      ⏳ Hạn mở: {b_info['expiry']}\n"
            bot.edit_message_text(ban_text, call.message.chat.id, call.message.message_id, reply_markup=get_back_btn("admin_mng_user"), parse_mode="Markdown")

    except Exception as e:
        print(f"Exception Admin Callback: {e}")

def get_back_btn(target):
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("⬅️ Quay Lại", callback_data=target))
    return markup

# ==========================================
# CÁC BƯỚC LOGIC ĐIỀU HƯỚNG NEXT STEP (ADMIN)
# ==========================================
def step_add_admin(message):
    try:
        new_id = int(message.text.strip())
        if new_id not in ADMINS:
            ADMINS.append(new_id)
            bot.reply_to(message, f"✅ Thêm thành công Admin đồng quyền mới: `{new_id}`", parse_mode="Markdown")
        else:
            bot.reply_to(message, "⚠️ Thành viên này đã có quyền quản trị tối cao từ trước.")
    except Exception:
        bot.reply_to(message, "❌ Lỗi: Bạn nhập sai định dạng chuỗi ID số.")

def step_change_avatar(message):
    try:
        url = message.text.strip()
        DB_CONFIG["banner_url"] = url
        bot.reply_to(message, "✅ Cập nhật thành công Link Avatar/Banner của hệ thống Bot.")
    except Exception as e:
        bot.reply_to(message, f"❌ Thất bại: {e}")

def step_change_bank(message):
    try:
        parts = message.text.split("|")
        DB_CONFIG["bank_name"] = parts[0].strip()
        DB_CONFIG["bank_account"] = parts[1].strip()
        DB_CONFIG["bank_holder"] = parts[2].strip()
        DB_CONFIG["bank_qr"] = f"https://api.vietqr.io/image/970422-{parts[1].strip()}-YL66FmK.jpg"
        bot.reply_to(message, "✅ Đã lưu thay đổi thông tin ngân hàng và đồng bộ mã VietQR mới thành công!")
    except Exception:
        bot.reply_to(message, "❌ Thất bại! Vui lòng nhập chuẩn theo cú pháp: Tên Ngân Hàng|Số Tài Khoản|Tên Chủ Tài Khoản")

def step_user_balance_modify(message, mode):
    try:
        uid_str, amt_str = message.text.split("|")
        target_uid = int(uid_str.strip())
        amount = int(amt_str.strip())
        
        if target_uid not in DB_USERS:
            bot.reply_to(message, "❌ Thành viên này chưa từng tồn tại hoặc chưa ấn /start bot.")
            return

        if mode == "add":
            DB_USERS[target_uid]["balance"] += amount
            DB_USERS[target_uid]["total_deposit"] += amount
            DB_REVENUE["deposit_today"] += amount
            bot.reply_to(message, f"✅ Đã cộng `+{amount:,} VND` cho khách hàng `{target_uid}`", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, f"🔔 **BIẾN ĐỘNG SỐ DƯ:** Tài khoản của bạn đã được Admin cộng thêm `+{amount:,} VND` vào ví.", parse_mode="Markdown")
            except Exception:
                pass
        else:
            DB_USERS[target_uid]["balance"] = max(0, DB_USERS[target_uid]["balance"] - amount)
            bot.reply_to(message, f"✅ Đã cấu trừ `-{amount:,} VND` của khách hàng `{target_uid}`", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, f"⚠️ **CẢNH BÁO:** Tài khoản của bạn đã bị Ban Quản Trị khấu trừ số tiền: `-{amount:,} VND`.", parse_mode="Markdown")
            except Exception:
                pass
    except Exception:
        bot.reply_to(message, "❌ Nhập sai cấu trúc định dạng. Định dạng chuẩn yêu cầu: UID|Số_Tiền")

def step_user_ban(message):
    try:
        uid_str, reason, days_str = message.text.split("|")
        target_uid = int(uid_str.strip())
        days = int(days_str.strip())
        
        b_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if days <= 0:
            expiry_str = "Vĩnh Viễn"
        else:
            expiry_str = (datetime.now() + timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")
            
        DB_BAN_LIST[target_uid] = {
            "ban_date": b_date,
            "reason": reason.strip(),
            "expiry": expiry_str
        }
        bot.reply_to(message, f"🛑 Đã thực thi lệnh cấm truy cập (BAN) tài khoản `{target_uid}` thành công.", parse_mode="Markdown")
        try:
            bot.send_message(target_uid, f"⚠️ Tài khoản của bạn đã bị khóa bởi hệ thống quản trị viên.\n🛑 Lý do: {reason}\n⏳ Thời hạn: {expiry_str}")
        except Exception:
            pass
    except Exception:
        bot.reply_to(message, "❌ Sai cấu trúc nhập liệu. Định dạng chuẩn: `UID|Lý_Do|Số_Ngày`")

def step_user_unban(message):
    try:
        target_uid = int(message.text.strip())
        if target_uid in DB_BAN_LIST:
            del DB_BAN_LIST[target_uid]
            bot.reply_to(message, f"🔓 Đã gỡ lệnh cấm (Unban) thành công cho ID: `{target_uid}`", parse_mode="Markdown")
            try:
                bot.send_message(target_uid, f"🎉 **CHÚC MỪNG:** Tài khoản của bạn đã được gỡ lệnh cấm. Hãy gõ lệnh /start để tiếp tục sử dụng dịch vụ.", parse_mode="Markdown")
            except Exception:
                pass
        else:
            bot.reply_to(message, "⚠️ Tài khoản này hiện không nằm trong danh sách đen bị cấm.")
    except Exception:
        bot.reply_to(message, "❌ Chỉ chấp nhận ký tự số nguyên của UID khách hàng.")

# ==========================================
# CƠ CHẾ PHÊ DUYỆT HOÁ ĐƠN NẠP TIỀN QUA INLINE
# ==========================================
@bot.callback_query_handler(func=lambda call: call.data.startswith('admapp_'))
def process_admin_approval_decide(call):
    try:
        if call.from_user.id not in ADMINS:
            return
        
        _, decision, target_uid_str = call.data.split("_")
        target_uid = int(target_uid_str)
        
        if decision == "yes":
            msg = bot.send_message(call.message.chat.id, f"💰 Nhập số tiền chính xác cần nạp cho tài khoản `{target_uid}`:")
            bot.register_next_step_handler(msg, step_finalize_approve, target_uid, call.message)
        else:
            try:
                bot.send_message(target_uid, "❌ **ĐƠN NẠP TIỀN BỊ TỪ CHỐI:** Giao dịch nạp tiền của bạn đã bị Ban Quản Trị từ chối do thông tin hình ảnh không hợp lệ hoặc sai cấu trúc nội dung chuyển khoản.")
            except Exception:
                pass
            bot.edit_message_caption("❌ ĐÃ TỪ CHỐI HỦY ĐƠN NẠP TIỀN CỦA KHÁCH HÀNG", call.message.chat.id, call.message.message_id)
    except Exception as e:
        print(f"Error approval decide: {e}")

def step_finalize_approve(message, target_uid, original_msg):
    try:
        money = int(message.text.strip())
        if target_uid in DB_USERS:
            DB_USERS[target_uid]["balance"] += money
            DB_USERS[target_uid]["total_deposit"] += money
            DB_REVENUE["deposit_today"] += money
            
            try:
                bot.send_message(target_uid, f"🎉 **NẠP TIỀN THÀNH CÔNG:** Hệ thống đã cộng thêm `+{money:,} VND` vào tài khoản của bạn.\n💰 Số dư hiện tại: `{DB_USERS[target_uid]['balance']:,} VND`.", parse_mode="Markdown")
            except Exception:
                pass
            bot.edit_message_caption(f"✅ ĐÃ PHÊ DUYỆT CỘNG THÀNH CÔNG `+{money:,} VND`", original_msg.chat.id, original_msg.message_id, parse_mode="Markdown")
        else:
            bot.reply_to(message, "❌ Lỗi: Tài khoản không tồn tại trên cơ sở dữ liệu đệm.")
    except Exception:
        bot.reply_to(message, "❌ Lỗi: Bạn phải nhập vào một số tiền là số nguyên hợp lệ.")

# ==========================================
# KIẾN TRÚC WEBHOOK FLASK VÀ GIẢI PHÓNG BỘ NHỚ
# ==========================================
@app.route('/', methods=['GET', 'HEAD'])
def index_check():
    return "Hệ thống Bot Mail 24H đang vận hành trực tuyến 24/7!", 200

@app.route(f'/{API_TOKEN}/', methods=['POST'])
def receive_webhook_updates():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return '', 200
    return 'Forbidden', 403

if __name__ == '__main__':
    # Giải phóng và giải trừ cài đặt liên kết cũ theo đúng quy định kiến trúc bảo mật
    bot.remove_webhook()
    time.sleep(1)
    bot.set_webhook(url=WEBHOOK_URL)
    
    # Khởi chạy hệ thống tự động bắt PORT trên hạ tầng đám mây Render.com
    port_run = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port_run)
