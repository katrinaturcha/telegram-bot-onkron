import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from aiogram.types import ReplyKeyboardMarkup
from dotenv import load_dotenv
import json
from google.oauth2.service_account import Credentials

# === Загружаем токен ===
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=TOKEN)
dp = Dispatcher(bot)

# === Настройка доступа к Google Sheets ===
scope = ["https://spreadsheets.google.com/feeds",
         "https://www.googleapis.com/auth/drive"]

creds_json = json.loads(os.getenv("CREDS_JSON"))
creds = Credentials.from_service_account_info(creds_json, scopes=scope)
client = gspread.authorize(creds)


# Название таблицы (введи своё!)
SHEET_NAME = "Telegram Bot Requests"
sheet = client.open(SHEET_NAME).sheet1

# === Главное меню ===
main_kb = ReplyKeyboardMarkup(resize_keyboard=True)
main_kb.add("📞 Заказать обратный звонок", "🏆 Участвую в конкурсе", "📦 Пришлите прайс")

# === Функция записи в Google Sheets ===
# === Функция записи в Google Sheets ===
def save_to_gsheet(user_id, username, phone, photo_url, req_type):
    # Новый порядок столбцов:
    # timestamp | user_id | username | request_type | phone | photo_url
    sheet.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        user_id,
        username or "",
        req_type,
        phone or "",
        photo_url or ""
    ])


# === Получение ссылки на фото ===
async def get_photo_url(file_id):
    file = await bot.get_file(file_id)
    return f"https://api.telegram.org/file/bot{TOKEN}/{file.file_path}"

# === Состояния ===
user_state = {}
user_phone = {}

# === /start ===
@dp.message_handler(commands=["start"])
async def start(msg: types.Message):
    user_state.pop(msg.from_user.id, None)
    await msg.answer("Привет! Выберите действие:", reply_markup=main_kb)

# === Обратный звонок ===
@dp.message_handler(lambda m: m.text == "📞 Заказать обратный звонок")
async def call_request(msg: types.Message):
    user_state[msg.from_user.id] = "callback"
    await msg.answer("Пожалуйста, введите ваш номер телефона начиная с + (например, +79991234567):")

@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "callback")
async def handle_callback_phone(msg: types.Message):
    phone = msg.text.strip()
    user = msg.from_user

    if not phone.startswith("+") or len(phone) < 10:
        await msg.answer("❌ Неверно введён номер. Введите начиная с +, например +79991234567")
        return

    save_to_gsheet(user.id, user.username, phone, "", "обратный звонок")
    user_state.pop(user.id, None)
    await msg.answer("✅ Спасибо! Наш специалист свяжется с вами в ближайшее время ☎️", reply_markup=main_kb)

# === Конкурс ===
@dp.message_handler(lambda m: m.text == "🏆 Участвую в конкурсе")
async def contest_start(msg: types.Message):
    user_state[msg.from_user.id] = "contest_wait_phone"
    await msg.answer("Введите, пожалуйста, свой номер телефона начиная с + (например, +79991234567):")


# === Проверка корректности номера ===
@dp.message_handler(lambda m: user_state.get(m.from_user.id) == "contest_wait_phone")
async def contest_check_phone(msg: types.Message):
    phone = msg.text.strip()

    # Проверяем формат: начинается с "+" и содержит >= 10 цифр
    if not phone.startswith("+") or len([c for c in phone if c.isdigit()]) < 10:
        await msg.answer("❌ Неверно введён номер. Введите начиная с +, например +79991234567")
        return

    user_state[msg.from_user.id] = "contest_wait_photo"
    user_phone[msg.from_user.id] = phone
    await msg.answer("✅ Номер принят! Теперь отправьте фото для конкурса 📸")

@dp.message_handler(content_types=["photo", "document"])
async def contest_photo(msg: types.Message):
    # Проверяем, действительно ли пользователь сейчас в режиме конкурса
    if user_state.get(msg.from_user.id) != "contest_wait_photo":
        return

    user = msg.from_user
    phone = user_phone.get(user.id, "")
    photo_url = None

    # === Если это обычное фото ===
    if msg.photo:
        photo_id = msg.photo[-1].file_id
        photo_url = await get_photo_url(photo_id)

    # === Если это документ, проверяем MIME-тип ===
    elif msg.document:
        mime = msg.document.mime_type.lower()

        # Проверяем, является ли документ изображением
        if mime in ["image/jpeg", "image/png", "image/jpg"]:
            photo_id = msg.document.file_id
            photo_url = await get_photo_url(photo_id)
        else:
            await msg.answer(
                "⚠️ Неверный формат файла.\n"
                "Пожалуйста, отправьте изображение в формате JPG, JPEG или PNG 📸"
            )
            return

    # === Если ни одно условие не сработало ===
    if not photo_url:
        await msg.answer(
            "⚠️ Это не похоже на изображение.\n"
            "Отправьте фото в формате JPG, JPEG или PNG 📸"
        )
        return

    # === Пишем данные в Google Sheets ===
    try:
        save_to_gsheet(user.id, user.username, phone, photo_url, "конкурс")
    except Exception as e:
        await msg.answer(f"⚠️ Не удалось записать в таблицу: {e}")
        return

    # === Сбрасываем состояние ===
    user_state.pop(user.id, None)
    user_phone.pop(user.id, None)

    # === Отправляем подтверждение ===
    await msg.answer("📸 Фото получено! Спасибо за участие в конкурсе 🎉", reply_markup=main_kb)



# === Прайс ===
@dp.message_handler(lambda m: m.text == "📦 Пришлите прайс")
async def send_price(msg: types.Message):
    pdf_path = "invoice.pdf"
    if os.path.exists(pdf_path):
        with open(pdf_path, "rb") as pdf:
            await bot.send_document(msg.chat.id, pdf, caption="📄 Ваш прайс-лист:")
        save_to_gsheet(msg.from_user.id, msg.from_user.username, "", "", "прайс")
        await msg.answer("✅ Прайс-лист отправлен!", reply_markup=main_kb)
    else:
        await msg.answer("⚠️ Файл invoice.pdf не найден в проекте.", reply_markup=main_kb)

if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
