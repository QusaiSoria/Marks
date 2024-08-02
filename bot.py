import requests
from bs4 import BeautifulSoup
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, CallbackContext, JobQueue
from urllib.parse import urljoin
import os
from flask import Flask
from threading import Thread
import uuid

# Define constants for the conversation states
DEPARTMENT_ID, YEAR, SEASON = range(3)

# Base URL of the website
BASE_URL = 'https://damascusuniversity.edu.sy/ite/'

# Get the Telegram bot token from the environment variable
token = os.environ.get('TELEGRAM_API_TOKEN')
another_bot_token = os.environ.get('ANOTHER_BOT_TOKEN')
another_bot_chat_id = os.environ.get('CHAT_ID')

# In-memory dictionary to track the number of times users clicked start
user_start_count = {}

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
    user_id = update.message.from_user.id
    username = update.message.from_user.username

    # Increment the start count for the user
    if user_id in user_start_count:
        user_start_count[user_id] += 1
    else:
        user_start_count[user_id] = 1

    # Send a message to another bot
    send_message_to_another_bot(user_id, username, user_start_count[user_id])

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

def send_message_to_another_bot(user_id, username, start_count):
    """Send a message to another bot with the user's information."""
    message = f"User ID: {user_id}\nUsername: @{username}\nStart Count: {start_count}"
    url = f"https://api.telegram.org/bot{another_bot_token}/sendMessage"
    data = {
        "chat_id": another_bot_chat_id,
        "text": message
    }
    requests.post(url, data=data)

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
    """Fetch and process data based on user inputs and prepare the files."""
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

    def fetch_page_data(url, post_data):
        """Fetch data from a single page."""
        try:
            response = requests.post(url, data=post_data, verify=False)
            response.encoding = 'utf-8'
            soup = BeautifulSoup(response.text, 'html.parser')
            return soup
        except requests.RequestException as e:
            update.effective_chat.send_message(f"فشل في جلب البيانات: {str(e)}")
            return None

    def process_table(soup):
        """Process the table data from the soup."""
        table = soup.find('table', {'border': '1'})
        if not table:
            return []

        rows = table.find_all('tr')
        if len(rows) <= 1:
            return []

        files = []
        for row in rows[1:]:
            cells = row.find_all('td')
            if len(cells) >= 7:
                title = cells[0].get_text(strip=True)
                link_tag = cells[6].find('a', href=True)
                if link_tag:
                    link = link_tag['href']
                    download_link = urljoin(BASE_URL, link)
                    files.append((title, download_link))
        return files

    def get_pagination_links(soup):
        """Get pagination links from the soup."""
        pagination_table = soup.find('table', {'align': 'center', 'width': '100%', 'border': '0', 'dir': 'rtl'})
        if not pagination_table:
            return []

        links = pagination_table.find_all('a', {'class': 'blankblueLink2'})
        return [urljoin(url, link['href']) for link in links]

    soup = fetch_page_data(url, post_data)
    if not soup:
        return

    files = process_table(soup)
    if not files:
        update.effective_chat.send_message('لم يتم العثور على بيانات للمعايير المحددة.')
        return

    pagination_links = get_pagination_links(soup)
    for link in pagination_links:
        soup = fetch_page_data(link, post_data)
        if soup:
            files.extend(process_table(soup))

    if files:
        show_files_as_buttons(update, context, files)
    else:
        update.effective_chat.send_message('لم يتم العثور على ملفات لإرسالها.')

def show_files_as_buttons(update: Update, context: CallbackContext, files):
    """Show the files as buttons to the user with pagination."""
    context.user_data['files'] = files
    context.user_data['file_mapping'] = {}
    context.user_data['current_page'] = 0

    show_page(update, context)

def show_page(update: Update, context: CallbackContext):
    """Show a specific page of file buttons."""
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

    # Calculate the total number of pages
    total_pages = (len(files) + files_per_page - 1) // files_per_page

    # Add navigation buttons if needed
    navigation_buttons = []
    if current_page > 0:
        navigation_buttons.append(InlineKeyboardButton('⬅️', callback_data='prev_page'))
    
    # Add page number information
    navigation_buttons.append(InlineKeyboardButton(f"{current_page + 1}/{total_pages}", callback_data='noop'))
    
    if end_index < len(files):
        navigation_buttons.append(InlineKeyboardButton('➡️', callback_data='next_page'))

    if navigation_buttons:
        keyboard.append(navigation_buttons)

    # Add a download all button if there are files
    if files:
        keyboard.append([InlineKeyboardButton('📦 تحميل جميع الملفات', callback_data='download_all')])

    reply_markup = InlineKeyboardMarkup(keyboard)
    if update.callback_query:
        update.callback_query.edit_message_text('اختر الملف الذي تريد تحميله:', reply_markup=reply_markup)
    else:
        update.message.reply_text('اختر الملف الذي تريد تحميله:', reply_markup=reply_markup)

def send_file(update: Update, context: CallbackContext):
    """Send the file when a button is clicked or handle pagination."""
    query = update.callback_query
    query.answer()
    data = query.data

    if data == 'prev_page':
        context.user_data['current_page'] -= 1
        show_page(update, context)
    elif data == 'next_page':
        context.user_data['current_page'] += 1
        show_page(update, context)
    elif data == 'download_all':
        download_all_files(update, context)
    else:
        file_url = context.user_data['file_mapping'].get(data)
        if file_url:
            # Send the "wait" sticker
            sticker_id = 'CAACAgQAAxkBAAEs6VxmqsXDjnmbmVbkueGsCBwF4BV9IgACSAoAAip5uFBmuCZY8V1p3zUE'  # Example sticker ID
            wait_message = query.message.reply_sticker(sticker_id)
            
            local_filename = os.path.basename(file_url)
            if download_file(file_url, local_filename):
                context.bot.send_document(chat_id=update.effective_chat.id, document=open(local_filename, 'rb'))
                os.remove(local_filename)
            else:
                query.message.reply_text('فشل في تنزيل الملف.')
            
            # Delete the "wait" sticker
            context.bot.delete_message(chat_id=wait_message.chat_id, message_id=wait_message.message_id)
        else:
            query.message.reply_text('فشل في العثور على الرابط.')

def download_all_files(update: Update, context: CallbackContext):
    """Download and send all files to the user."""
    files = context.user_data['files']
    if not files:
        update.callback_query.message.reply_text('لم يتم العثور على ملفات لتنزيلها.')
        return

    for title, file_url in files:
        local_filename = os.path.basename(file_url)
        if download_file(file_url, local_filename):
            context.bot.send_document(chat_id=update.effective_chat.id, document=open(local_filename, 'rb'))
            os.remove(local_filename)
        else:
            update.callback_query.message.reply_text(f'فشل في تنزيل الملف: {title}')

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
        'يمكنك التواصل بمطور البوت من خلال المعرف : @Qusai_Salwm'
        
    )
    
def cancel(update: Update, context: CallbackContext) -> int:
    update.message.reply_text('تم إلغاء العملية.')
    return ConversationHandler.END

def periodic_task(context: CallbackContext):
    """Task to be executed periodically."""
    context.bot.send_message(chat_id=os.environ.get('CHAT_ID'), text="Running periodic task...")
    # Here you can call any function or perform any task you need to run periodically.
    # For example, fetch_and_process_data can be called if you want to fetch and process data periodically.
    # update and context should be properly passed or mocked.

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
    
    # Add handler for file button clicks and pagination
    dp.add_handler(CallbackQueryHandler(send_file, pattern='^[a-f0-9\-]+$|prev_page|next_page|download_all'))

    # Add handler for the contact command
    dp.add_handler(CommandHandler('contact', contact))
    
    # Get the job queue
    job_queue = updater.job_queue

    # Schedule the periodic task every 40 seconds
    job_queue.run_repeating(periodic_task, interval=40, first=0)

    
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
