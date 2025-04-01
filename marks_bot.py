import os
from flask import Flask, request, Response
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ConversationHandler, CallbackContext
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import uuid

# Define constants for the conversation states
DEPARTMENT_ID, YEAR, SEASON = range(3)

# Base URL of the website
BASE_URL = 'https://damascusuniversity.edu.sy/ite/'

# Initialize Flask app
app_flask = Flask(__name__)

# Get the Telegram bot token from environment variables
TOKEN = os.environ.get('TELEGRAM_TOKEN', '7211468470:AAGCOqhw5MJjsLYyb1HZDr4NQQDu-6H5kSA')
ANOTHER_BOT_TOKEN = os.environ.get('ANOTHER_BOT_TOKEN', '7445301702:AAHi3yqzGQIh4XXIQZSWyen1k_6QoddbUGw')
ANOTHER_BOT_CHAT_ID = int(os.environ.get('ANOTHER_BOT_CHAT_ID', '819385459'))

# In-memory dictionary to track the number of times users clicked start
user_start_count = {}

# Define department, year, and season options
department_options = [
    ('جميع التخصصات', '-1'), ('الذكاء الصنعي', '1'), ('الشبكات', '5'),
    ('البرمجيات', '2'), ('العلوم الأساسية', '3')
]
year_options = [
    ('2025', '2025'), ('2024', '2024'), ('2023', '2023'),
    ('2022', '2022'), ('2021', '2021'), ('2020', '2020')
]
season_options = [
    ('الفصل الأول', '1'), ('الفصل الثاني', '2'), ('الفصلين', '-1')
]

# Telegram bot application setup
bot_app = Application.builder().token(TOKEN).build()

def start(update: Update, context: CallbackContext) -> int:
    user_id = update.message.from_user.id
    username = update.message.from_user.username
    user_start_count[user_id] = user_start_count.get(user_id, 0) + 1
    send_message_to_another_bot(user_id, username, user_start_count[user_id])

    keyboard = [[InlineKeyboardButton(text, callback_data=value)] for text, value in department_options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        'مرحبا ببوت استخراج ملفات العلامات لكلية الهندسة المعلوماتية بدمشق\nاختر القسم:',
        reply_markup=reply_markup
    )
    return DEPARTMENT_ID

def send_message_to_another_bot(user_id, username, start_count):
    message = f"User ID: {user_id}\nUsername: @{username}\nStart Count: {start_count}"
    url = f"https://api.telegram.org/bot{ANOTHER_BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": ANOTHER_BOT_CHAT_ID, "text": message})

def get_department_id(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['department_id'] = query.data
    
    keyboard = []
    for i in range(0, len(year_options), 2):
        row = [InlineKeyboardButton(year_options[i][0], callback_data=year_options[i][1])]
        if i + 1 < len(year_options):
            row.append(InlineKeyboardButton(year_options[i + 1][0], callback_data=year_options[i + 1][1]))
        keyboard.append(row)
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text('اختر العام:', reply_markup=reply_markup)
    return YEAR

def get_year(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['year'] = query.data
    
    keyboard = [[InlineKeyboardButton(text, callback_data=value)] for text, value in season_options]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text('اختر الفصل الدراسي:', reply_markup=reply_markup)
    return SEASON

def get_season(update: Update, context: CallbackContext) -> int:
    query = update.callback_query
    query.answer()
    context.user_data['season'] = query.data
    
    query.edit_message_text('يتم معالجة الطلب و ارسال الملفات ...')
    fetch_and_process_data(update, context)
    return ConversationHandler.END

def fetch_and_process_data(update: Update, context: CallbackContext):
    post_data = {
        'func': '2', 'set': '14', 'College': '', 'Category': '0', 'lang': '1',
        'CStadyYear': '', 'department_id': context.user_data['department_id'],
        'StadyYear': '', 'Year': context.user_data['year'], 'Season': context.user_data['season']
    }
    url = 'https://damascusuniversity.edu.sy/ite/index.php'

    def fetch_page_data(url, post_data):
        try:
            response = requests.post(url, data=post_data, verify=False)
            response.encoding = 'utf-8'
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            update.effective_chat.send_message(f"فشل في جلب البيانات: {str(e)}")
            return None

    def process_table(soup):
        table = soup.find('table', {'border': '1'})
        if not table or len(table.find_all('tr')) <= 1:
            return []
        files = []
        for row in table.find_all('tr')[1:]:
            cells = row.find_all('td')
            if len(cells) >= 7 and (link_tag := cells[6].find('a', href=True)):
                files.append((cells[0].get_text(strip=True), urljoin(BASE_URL, link_tag['href'])))
        return files

    def get_pagination_links(soup):
        pagination = soup.find('table', {'align': 'center', 'width': '100%', 'border': '0', 'dir': 'rtl'})
        return [urljoin(url, link['href']) for link in pagination.find_all('a', {'class': 'blankblueLink2'})] if pagination else []

    soup = fetch_page_data(url, post_data)
    if not soup:
        return
    files = process_table(soup)
    if not files:
        update.effective_chat.send_message('لم يتم العثور على بيانات للمعايير المحددة.')
        return

    for link in get_pagination_links(soup):
        if soup := fetch_page_data(link, post_data):
            files.extend(process_table(soup))

    files and show_files_as_buttons(update, context, files) or update.effective_chat.send_message('لم يتم العثور على ملفات لإرسالها.')

def show_files_as_buttons(update: Update, context: CallbackContext, files):
    context.user_data.update({'files': files, 'file_mapping': {}, 'current_page': 0})
    show_page(update, context)

def show_page(update: Update, context: CallbackContext):
    files = context.user_data['files']
    file_mapping = context.user_data['file_mapping']
    current_page = context.user_data['current_page']
    files_per_page = 12

    start_index = current_page * files_per_page
    end_index = start_index + files_per_page
    page_files = files[start_index:end_index]

    keyboard = []
    for title, link in page_files:
        identifier = str(uuid.uuid4())
        file_mapping[identifier] = link
        keyboard.append([InlineKeyboardButton(title, callback_data=identifier)])

    total_pages = (len(files) + files_per_page - 1) // files_per_page
    navigation_buttons = []
    if current_page > 0:
        navigation_buttons.append(InlineKeyboardButton('⬅️', callback_data='prev_page'))
    navigation_buttons.append(InlineKeyboardButton(f" 📄 {current_page + 1}/{total_pages}", callback_data='noop'))
    if end_index < len(files):
        navigation_buttons.append(InlineKeyboardButton('➡️', callback_data='next_page'))

    if navigation_buttons:
        keyboard.append(navigation_buttons)
    if files:
        keyboard.append([InlineKeyboardButton(f'📦 تحميل جميع الملفات ({len(files)})', callback_data='download_all')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    text = 'اختر الملف الذي تريد تحميله:'
    if update.callback_query:
        update.callback_query.edit_message_text(text, reply_markup=reply_markup)
    else:
        update.message.reply_text(text, reply_markup=reply_markup)

def send_file(update: Update, context: CallbackContext):
    query = update.callback_query
    query.answer()
    data = query.data

    if data in ('prev_page', 'next_page'):
        context.user_data['current_page'] += -1 if data == 'prev_page' else 1
        show_page(update, context)
    elif data == 'download_all':
        download_all_files(update, context)
    elif (file_url := context.user_data['file_mapping'].get(data)):
        sticker_id = 'CAACAgQAAxkBAALq9WeRSdM9hkXoRxz6bg7-i0gplncGAAJdAAOp1HEBioo4tsUUfq0eBA'
        wait_message = query.message.reply_sticker(sticker_id)
        local_filename = os.path.basename(file_url)
        if download_file(file_url, local_filename):
            context.bot.send_document(chat_id=update.effective_chat.id, document=open(local_filename, 'rb'))
            os.remove(local_filename)
        else:
            query.message.reply_text('فشل في تنزيل الملف.')
        context.bot.delete_message(chat_id=wait_message.chat_id, message_id=wait_message.message_id)
    else:
        query.message.reply_text('فشل في العثور على الرابط.')

def download_all_files(update: Update, context: CallbackContext):
    files = context.user_data['files']
    if not files:
        update.callback_query.message.reply_text('لم يتم العثور على ملفات لتنزيلها.')
        return

    update.callback_query.message.reply_text('جاري تنزيل الملفات...')
    for title, file_url in files:
        local_filename = os.path.basename(file_url)
        if download_file(file_url, local_filename):
            context.bot.send_document(chat_id=update.effective_chat.id, document=open(local_filename, 'rb'))
            os.remove(local_filename)
        else:
            update.callback_query.message.reply_text(f'فشل في تنزيل الملف: {title}')
    update.callback_query.message.reply_text('تم تنزيل جميع الملفات بنجاح.')

def download_file(url, local_filename):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    return False

def contact(update: Update, context: CallbackContext):
    update.message.reply_text('يمكنك التواصل بمطور البوت من خلال المعرف : @Qusai_Salwm')

def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('تم إلغاء العملية.')
    return ConversationHandler.END

# Flask route for Telegram webhook
@app_flask.route('/webhook', methods=['POST'])
def webhook():
    update = Update.de_json(request.get_json(), bot_app.bot)
    bot_app.process_update(update)
    return Response(status=200)

@app_flask.route('/')
def index():
    return "Bot is running!"

# Set up the Telegram bot handlers
conv_handler = ConversationHandler(
    entry_points=[CommandHandler('start', start)],
    states={
        DEPARTMENT_ID: [CallbackQueryHandler(get_department_id)],
        YEAR: [CallbackQueryHandler(get_year)],
        SEASON: [CallbackQueryHandler(get_season)],
    },
    fallbacks=[CommandHandler('cancel', cancel)]
)

bot_app.add_handler(conv_handler)
bot_app.add_handler(CallbackQueryHandler(send_file, pattern=r'^[a-f0-9\-]+$|prev_page|next_page|download_all'))
bot_app.add_handler(CommandHandler('contact', contact))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app_flask.run(host='0.0.0.0', port=port)
