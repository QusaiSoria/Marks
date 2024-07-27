import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, CallbackContext
from urllib.parse import urljoin
import os
from flask import Flask
from threading import Thread
# Define constants for the conversation states
DEPARTMENT_ID, YEAR, SEASON = range(3)

# Base URL of the website
BASE_URL = 'https://damascusuniversity.edu.sy/ite/'
token = os.environ.get('TELEGRAM_API_TOKEN')

# Define department options
department_options = [
    ('جميع التخصصات', '-1'),
    ('الذكاء الصنعي', '1'),
    ('الشبكات', '5'),
    ('البرمجيات', '2'),
    ('العلوم الأساسية', '3')
]

# Define year options
year_options = [
    ('2024', '2024'),
    ('2023', '2023'),
    ('2022', '2022'),
    ('2021', '2021'),
    ('2020', '2020')
]

# Define season options
season_options = [
    ('الفصل الأول', '1'),
    ('الفصل الثاني', '2'),
    ('الفصلين', '-1')
]

def start(update: Update, context: CallbackContext) -> int:
    """Send a message when the command /start is issued."""
    keyboard = [
        [InlineKeyboardButton(text, callback_data=value)] for text, value in department_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text(
        'مرحبا ببوت استخراج ملفات العلامات لكلية الهندسة المعلوماتية بدمشق\n'
        'اختر القسم :',
        reply_markup=reply_markup
    )
    return DEPARTMENT_ID

def get_department_id(update: Update, context: CallbackContext) -> int:
    """Get the department_id from the user."""
    query = update.callback_query
    query.answer()
    context.user_data['department_id'] = query.data
    
    # Create a keyboard with two year options per row
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
    """Get the year from the user."""
    query = update.callback_query
    query.answer()
    context.user_data['year'] = query.data
    
    keyboard = [
        [InlineKeyboardButton(text, callback_data=value)] for text, value in season_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    query.edit_message_text('اختر الفصل الدراسي:', reply_markup=reply_markup)
    
    return SEASON

def get_season(update: Update, context: CallbackContext) -> int:
    """Get the season from the user."""
    query = update.callback_query
    query.answer()
    context.user_data['season'] = query.data
    
    query.edit_message_text('يتم معالجة الطلب و ارسال الملفات ...')
    
    fetch_and_process_data(update, context)
    return ConversationHandler.END

def fetch_and_process_data(update: Update, context: CallbackContext):
    """Fetch and process data based on user inputs and upload the files."""
    post_data = {
        'func': '2',  # Function
        'set': '14',  # Set
        'College': '',  # Branch
        'Category': '0',  # Category
        'lang': '1',  # Language
        'CStadyYear': '',  # Study Year
        'department_id': context.user_data['department_id'],  # Department ID
        'StadyYear': '',  # Study Year
        'Year': context.user_data['year'],  # Year
        'Season': context.user_data['season']  # Season
    }

    url = 'https://damascusuniversity.edu.sy/ite/index.php'

    try:
        response = requests.post(url, data=post_data, verify=False)
        response.encoding = 'utf-8'
        soup = BeautifulSoup(response.text, 'html.parser')
        table = soup.find('table', {'border': '1'})
        if not table:
            update.effective_chat.send_message('لم يتم العثور على بيانات للمعايير المحددة.')
            return
        
        rows = table.find_all('tr')
        if len(rows) <= 1:
            update.effective_chat.send_message('لم يتم العثور على بيانات للمعايير المحددة.')
            return

        files_sent = 0
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) >= 7:
                title = cells[0].get_text(strip=True)
                department = cells[1].get_text(strip=True)
                year = cells[2].get_text(strip=True)
                academic_year = cells[3].get_text(strip=True)
                season = cells[4].get_text(strip=True)
                teacher = cells[5].get_text(strip=True)
                link_tag = cells[6].find('a', href=True)
                if link_tag:
                    link = link_tag['href']
                    download_link = urljoin(BASE_URL, link)
                    local_filename = os.path.basename(download_link)
                    if download_file(download_link, local_filename):
                        context.bot.send_document(chat_id=update.effective_chat.id, document=open(local_filename, 'rb'))
                        os.remove(local_filename)
                        files_sent += 1
                    else:
                        update.effective_chat.send_message(f'فشل في تنزيل الملف: {title}')
        
        if files_sent > 0:
            update.effective_chat.send_message('تم إرسال جميع الملفات بنجاح.')
        else:
            update.effective_chat.send_message('لم يتم العثور على ملفات لإرسالها.')

    except requests.RequestException as e:
        update.effective_chat.send_message(f"فشل في جلب البيانات: {str(e)}")

def download_file(url, local_filename):
    response = requests.get(url, stream=True)
    if response.status_code == 200:
        with open(local_filename, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    else:
        return False

def contact(update: Update, context: CallbackContext):
    """Send a message with the developer's contact information."""
    update.message.reply_text(
        'يمكنك التواصل بمطور البوت من خلال المعرف : @Quasi_Salwm'
        
    )
    
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('تم إلغاء العملية.')
    return ConversationHandler.END

# Flask app for keeping Render happy
app = Flask('')

@app.route('/')
def home():
    return "I am alive"

def run():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run)
    t.start()

def main():
    """Start the bot."""
    keep_alive()  # Start the dummy HTTP server
    updater = Updater(token, use_context=True)

    dp = updater.dispatcher

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            DEPARTMENT_ID: [CallbackQueryHandler(get_department_id)],
            YEAR: [CallbackQueryHandler(get_year)],
            SEASON: [CallbackQueryHandler(get_season)],
        },
        fallbacks=[CommandHandler('cancel', cancel)]
    )

    dp.add_handler(conv_handler)
    
    # Add handler for the contact command
    dp.add_handler(CommandHandler('contact', contact))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()