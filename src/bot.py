import logging
import os
from datetime import datetime
from os.path import join as pjoin
import yadisk

import asyncio
from dotenv import load_dotenv
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters.command import Command
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter


# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

# Initialize bot with local API server for large file support
logging.info("Initialize bot with local API server...")
bot = Bot(
    token=os.getenv("BOT_TOKEN"),
    session=AiohttpSession(
        api=TelegramAPIServer(
            base="http://localhost:8081/bot{token}/{method}",
            file="http://localhost:8081/file/bot{token}/{path}"
        )
    )
)
logging.info("Initialize bot with local API server: DONE")
dp = Dispatcher()

# Global variables
yandex_disk_token: str = os.getenv("YADISK_TOKEN")
save_folder: str = "/ChatMediaBackup"  # Default folder

# FSM States
class CredentialsForm(StatesGroup):
    waiting_for_yandex_token = State()
    waiting_for_folder_path = State()

@dp.message(Command('start'))
async def send_welcome(message: Message):
    await message.reply(
        "📸 Welcome to Chat Media Backup Bot!\n\n"
        "This bot automatically saves all photos and videos sent to this chat to your Yandex Disk.\n\n"
        "To get started, use /set_yandex_disk_token to configure your Yandex Disk token."
    )

@dp.message(Command('help'))
async def send_help(message: Message):
    help_text = (
        "Available commands:\n\n"
        "🔹 /start - Start the bot\n"
        "🔹 /help - Show this help message\n"
        "🔹 /set_yandex_disk_token - Set Yandex Disk token\n"
        "🔹 /set_folder - Set custom folder path on Yandex Disk\n"
        "🔹 /status - Check bot status\n\n"
        "📝 The bot will automatically save all photos and videos sent to this chat to your Yandex Disk.\n"
        "Files are saved with format: timestamp_user_chatname.ext"
    )
    await message.answer(help_text)

@dp.message(Command('status'))
async def send_status(message: Message):
    global yandex_disk_token, save_folder
    
    if yandex_disk_token:
        try:
            yandex_disk_client = yadisk.Client(token=yandex_disk_token)
            if yandex_disk_client.check_token():
                status_text = "✅ Bot is ready to save media files!\n\n"
                status_text += "📁 Yandex Disk: Connected\n"
                status_text += f"📂 Save folder: {save_folder}\n"
                status_text += "🤖 Bot: Active"
            else:
                status_text = "❌ Yandex Disk token is invalid or expired.\n\n"
                status_text += "Please use /set_yandex_disk_token to update your token."
        except Exception as e:
            status_text = f"❌ Error checking Yandex Disk connection: {str(e)}"
    else:
        status_text = "⚠️ Yandex Disk token not configured.\n\n"
        status_text += "Use /set_yandex_disk_token to set your token."
    
    await message.answer(status_text)

@dp.message(Command('set_yandex_disk_token'))
async def get_yandex_disk_token(message: Message, state: FSMContext):
    await state.set_state(CredentialsForm.waiting_for_yandex_token)
    await message.reply("Please provide your Yandex Disk token:")

@dp.message(StateFilter(CredentialsForm.waiting_for_yandex_token))
async def process_yandex_token(message: Message, state: FSMContext):
    global yandex_disk_token
    
    token = message.text.strip()
    
    if not token:
        await message.reply("Token cannot be empty")
        return
    
    try:
        if not token.startswith('y0_'):
            await message.reply("⚠️ Token format seems invalid. Yandex Disk tokens usually start with 'y0_'")
            return
        
        yandex_disk_token = token
        
        try:
            await message.delete()
        except Exception as e:
            logging.warning(f"Could not delete token message: {e}")
        
        await message.answer("✅ Yandex Disk token stored successfully!")
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error setting Yandex Disk token: {e}")
        await message.reply("❌ Error updating token. Please try again.")

@dp.message(Command('set_folder'))
async def get_folder_path(message: Message, state: FSMContext):
    global save_folder
    await state.set_state(CredentialsForm.waiting_for_folder_path)
    await message.reply(
        f"Please provide the folder path on Yandex Disk where files should be saved.\n\n"
        f"Current folder: {save_folder}\n\n"
        f"Example: /MyMediaBackup or /Photos/TelegramBackup"
    )

@dp.message(StateFilter(CredentialsForm.waiting_for_folder_path))
async def process_folder_path(message: Message, state: FSMContext):
    global save_folder
    
    folder_path = message.text.strip()
    
    if not folder_path:
        await message.reply("Folder path cannot be empty")
        return
    
    try:
        # Ensure path starts with /
        if not folder_path.startswith('/'):
            folder_path = '/' + folder_path
        
        # Remove any unsafe characters
        safe_path = "".join(c for c in folder_path if c.isalnum() or c in ('/', '-', '_', ' '))
        
        save_folder = safe_path
        
        await message.answer(f"✅ Folder path updated to: {save_folder}")
        await state.clear()
        
    except Exception as e:
        logging.error(f"Error setting folder path: {e}")
        await message.reply("❌ Error updating folder path. Please try again.")

async def get_chat_name_for_filename(chat):
    """Get a safe chat name for filename"""
    if chat.type == 'private':
        return f"Private_{chat.id}"
    elif chat.title:
        # Replace unsafe characters for filenames
        safe_title = "".join(c for c in chat.title if c.isalnum() or c in ('-', '_')).strip()
        return safe_title if safe_title else f"Chat_{chat.id}"
    else:
        return f"Chat_{chat.id}"

async def upload_media_to_yandex_disk(file_path: str, filename: str) -> bool:
    """Upload media file to Yandex Disk"""
    global yandex_disk_token, save_folder
    
    if not yandex_disk_token:
        raise Exception("Yandex Disk token not set.")
    
    try:
        yandex_disk_client = yadisk.Client(token=yandex_disk_token)
        
        if not yandex_disk_client.check_token():
            raise Exception("Yandex Disk token is invalid or expired.")
        
        # Create directory if it doesn't exist
        if not yandex_disk_client.exists(save_folder):
            yandex_disk_client.mkdir(save_folder)
            logging.info(f"Created directory: {save_folder}")
        
        # Upload file
        remote_file_path = pjoin(save_folder, filename)
        
        # Check if file already exists and add counter if needed
        counter = 1
        original_filename = filename
        while yandex_disk_client.exists(remote_file_path):
            name, ext = os.path.splitext(original_filename)
            filename = f"{name}_{counter}{ext}"
            remote_file_path = pjoin(save_folder, filename)
            counter += 1
        
        yandex_disk_client.upload(file_path, remote_file_path)
        logging.info(f"Uploaded {filename} to {remote_file_path}")
        return True
        
    except Exception as e:
        logging.error(f"Error uploading to Yandex Disk: {e}")
        raise e

async def download_and_save_media(message: Message):
    """Download media from message and save to Yandex Disk"""
    try:
        chat_name = await get_chat_name_for_filename(message.chat)
        
        # Determine file info based on message type
        if message.photo:
            # Get the highest resolution photo
            photo = message.photo[-1]
            file_info = await bot.get_file(photo.file_id)
            file_ext = ".jpg"
            file_size = photo.file_size
        elif message.video:
            file_info = await bot.get_file(message.video.file_id)
            file_ext = ".mp4"
            file_size = message.video.file_size
        elif message.document and message.document.mime_type and message.document.mime_type.startswith(('image/', 'video/')):
            file_info = await bot.get_file(message.document.file_id)
            file_ext = os.path.splitext(message.document.file_name or "")[1] or ".file"
            file_size = message.document.file_size
        else:
            return False
        
        # With local API server, we can handle much larger files
        # Log file size for monitoring
        if file_size:
            logging.info(f"Processing file of size: {file_size / 1024 / 1024:.2f} MB")
        
        # Generate filename: timestamp_user_chatname.ext
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        username = message.from_user.username or f"user{message.from_user.id}"
        filename = f"{timestamp}_{username}_{chat_name}{file_ext}"
        
        # Download file to temporary location
        temp_file_path = f"/tmp/{filename}"
        await bot.download_file(file_info.file_path, temp_file_path)
        
        # Upload to Yandex Disk
        await upload_media_to_yandex_disk(temp_file_path, filename)
        
        # Clean up temporary file
        os.remove(temp_file_path)
        
        # Send confirmation (only in private chats to avoid spam)
        if message.chat.type == 'private':
            await message.reply(f"✅ Media saved to Yandex Disk as: {filename}")
        
        return True
        
    except Exception as e:
        logging.error(f"Error processing media: {e}")
        if message.chat.type == 'private':
            await message.reply(f"❌ Failed to save media: {str(e)}")
        return False

# Handle photos
@dp.message(F.photo)
async def handle_photo(message: Message):
    global yandex_disk_token
    
    if not yandex_disk_token:
        if message.chat.type == 'private':
            await message.reply("⚠️ Yandex Disk token not configured. Use /set_yandex_disk_token first.")
        return
    
    await download_and_save_media(message)

# Handle videos
@dp.message(F.video)
async def handle_video(message: Message):
    global yandex_disk_token
    
    if not yandex_disk_token:
        if message.chat.type == 'private':
            await message.reply("⚠️ Yandex Disk token not configured. Use /set_yandex_disk_token first.")
        return
    
    await download_and_save_media(message)

# Handle documents (if they are media files)
@dp.message(F.document)
async def handle_document(message: Message):
    global yandex_disk_token
    
    if not yandex_disk_token:
        return
    
    # Only process if it's an image or video document
    if message.document.mime_type and message.document.mime_type.startswith(('image/', 'video/')):
        await download_and_save_media(message)
        
async def main():
    while True:
        try:            
            # Set up commands for the bot menu
            await bot.set_my_commands([
                types.BotCommand(command="start", description="Start the bot"),
                types.BotCommand(command="help", description="Show available commands"),
                types.BotCommand(command="set_yandex_disk_token", description="Set Yandex Disk token"),
                types.BotCommand(command="set_folder", description="Set custom folder path"),
                types.BotCommand(command="status", description="Check bot status"),
            ])
            # Start polling
            await dp.start_polling(bot, polling_timeout=30)

        except Exception as e:
            logging.error(f"Connection error: {e}")
            logging.info("Retrying in 5 seconds...")
            await asyncio.sleep(5)
            continue

# Run the bot
if __name__ == '__main__':
    asyncio.run(main())