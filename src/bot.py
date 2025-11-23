import typing as t
import logging
import os
import tempfile
import subprocess
import requests
from requests import Session
from dotenv import load_dotenv
from datetime import datetime
import re
from os.path import join as pjoin
import yadisk

import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters.command import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.enums import ParseMode
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.filters import StateFilter

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)

assert os.getenv("BOT_TOKEN") is not None

# Initialize bot and dispatcher
bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()

# Global variables for storing credentials in RAM
yandex_disk_token: str = None

