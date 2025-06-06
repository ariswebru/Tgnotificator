
#!/usr/bin/env python3
"""
Telegram Bot для уведомлений о задачах - Архивная версия
Требует установки: pip install python-telegram-bot supabase
"""

import asyncio
import logging
import os
import json
from datetime import datetime
from typing import Dict, Optional

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from supabase import create_client, Client

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if not all([TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_KEY, TELEGRAM_CHAT_ID]):
    raise ValueError("Необходимо установить переменные окружения: TELEGRAM_BOT_TOKEN, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, TELEGRAM_CHAT_ID")

# Инициализация Supabase клиента
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

class TaskBot:
    def __init__(self):
        self.app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Настройка обработчиков команд и колбэков"""
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("my_tasks", self.my_tasks_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CallbackQueryHandler(self.handle_callback))
    
    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /start"""
        welcome_text = """
🤖 Добро пожаловать в бота уведомлений о задачах!

Доступные команды:
/my_tasks - Показать мои задачи
/help - Помощь

Бот автоматически отправляет уведомления о новых задачах в эту группу.
Только назначенные пользователи могут видеть детали своих задач.
        """
        await update.message.reply_text(welcome_text)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик команды /help"""
        help_text = """
📋 Помощь по боту задач

Команды:
• /start - Приветствие
• /my_tasks - Ваши текущие задачи
• /help - Эта справка

Уведомления:
Бот отправляет уведомления о:
• Новых задачах
• Изменении статуса задач
• Назначении задач на вас
• Приближающихся дедлайнах

Для получения уведомлений убедитесь, что:
1. Вы указали Telegram username в профиле
2. Включены уведомления в настройках
3. Вы находитесь в рабочей группе
        """
        await update.message.reply_text(help_text)
    
    async def my_tasks_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Показать задачи пользователя"""
        try:
            telegram_username = update.effective_user.username
            if not telegram_username:
                await update.message.reply_text(
                    "❌ Не удалось определить ваш Telegram username."
                )
                return
            
            user_response = supabase.table('profiles').select('id, first_name, last_name').eq('telegram_username', telegram_username).execute()
            
            if not user_response.data:
                await update.message.reply_text(
                    f"❌ Пользователь @{telegram_username} не найден в системе."
                )
                return
            
            user = user_response.data[0]
            tasks_response = supabase.table('tasks').select('*').eq('assigned_to', user['id']).neq('status', 'completed').execute()
            
            if not tasks_response.data:
                await update.message.reply_text(
                    f"📋 У вас нет активных задач, {user['first_name']}!"
                )
                return
            
            tasks_text = f"📋 Ваши активные задачи, {user['first_name']}:\n\n"
            
            for i, task in enumerate(tasks_response.data, 1):
                status_emoji = {
                    'todo': '⏳',
                    'in_progress': '🔄',
                    'review': '👀',
                    'cancelled': '❌'
                }.get(task['status'], '📝')
                
                priority_emoji = {
                    'low': '🟢',
                    'medium': '🟡',
                    'high': '🔴',
                    'urgent': '🚨'
                }.get(task['priority'], '⚪')
                
                due_date = ""
                if task['due_date']:
                    due_date = f"\n📅 Срок: {datetime.fromisoformat(task['due_date'].replace('Z', '+00:00')).strftime('%d.%m.%Y')}"
                
                tasks_text += f"{i}. {status_emoji} {task['title']}\n"
                tasks_text += f"   {priority_emoji} Приоритет: {task['priority']}{due_date}\n\n"
            
            keyboard = []
            for task in tasks_response.data[:5]:
                keyboard.append([
                    InlineKeyboardButton(
                        f"📝 {task['title'][:30]}...", 
                        callback_data=f"task_details_{task['id']}"
                    )
                ])
            
            reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
            await update.message.reply_text(tasks_text, reply_markup=reply_markup)
            
        except Exception as e:
            logger.error(f"Error in my_tasks_command: {e}")
            await update.message.reply_text("❌ Произошла ошибка при получении задач.")
    
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик inline кнопок"""
        query = update.callback_query
        await query.answer()
        
        try:
            callback_data = query.data
            telegram_username = update.effective_user.username
            
            if not telegram_username:
                await query.edit_message_text("❌ Не удалось определить ваш Telegram username.")
                return
            
            if callback_data.startswith('show_task_'):
                parts = callback_data.split('_')
                if len(parts) >= 4:
                    task_id = parts[2]
                    user_id = parts[3]
                    
                    user_response = supabase.table('profiles').select('id').eq('telegram_username', telegram_username).eq('id', user_id).execute()
                    
                    if not user_response.data:
                        await query.edit_message_text("❌ У вас нет прав для просмотра этой задачи.")
                        return
                    
                    task_response = supabase.table('tasks').select('*').eq('id', task_id).execute()
                    
                    if not task_response.data:
                        await query.edit_message_text("❌ Задача не найдена.")
                        return
                    
                    task = task_response.data[0]
                    await self.show_task_details(query, task)
            
            elif callback_data.startswith('task_details_'):
                task_id = callback_data.replace('task_details_', '')
                
                user_response = supabase.table('profiles').select('id').eq('telegram_username', telegram_username).execute()
                
                if not user_response.data:
                    await query.edit_message_text("❌ Пользователь не найден.")
                    return
                
                user_id = user_response.data[0]['id']
                task_response = supabase.table('tasks').select('*').eq('id', task_id).eq('assigned_to', user_id).execute()
                
                if not task_response.data:
                    await query.edit_message_text("❌ Задача не найдена или у вас нет прав доступа.")
                    return
                
                task = task_response.data[0]
                await self.show_task_details(query, task)
            
            elif callback_data.startswith('update_status_'):
                parts = callback_data.split('_')
                if len(parts) >= 4:
                    task_id = parts[2]
                    new_status = parts[3]
                    await self.update_task_status(query, task_id, new_status, telegram_username)
        
        except Exception as e:
            logger.error(f"Error in handle_callback: {e}")
            await query.edit_message_text("❌ Произошла ошибка при обработке запроса.")
    
    async def show_task_details(self, query, task: Dict):
        """Показать детали задачи"""
        status_text = {
            'todo': '⏳ К выполнению',
            'in_progress': '🔄 В работе',
            'review': '👀 На проверке',
            'completed': '✅ Выполнено',
            'cancelled': '❌ Отменено'
        }.get(task['status'], task['status'])
        
        priority_text = {
            'low': '🟢 Низкий',
            'medium': '🟡 Средний',
            'high': '🔴 Высокий',
            'urgent': '🚨 Срочный'
        }.get(task['priority'], task['priority'])
        
        due_date_text = ""
        if task['due_date']:
            due_date = datetime.fromisoformat(task['due_date'].replace('Z', '+00:00'))
            due_date_text = f"\n📅 Срок: {due_date.strftime('%d.%m.%Y %H:%M')}"
        
        estimated_hours = f"\n⏰ Оценка: {task['estimated_hours']} ч." if task['estimated_hours'] else ""
        actual_hours = f"\n⏱️ Затрачено: {task['actual_hours']} ч." if task['actual_hours'] else ""
        
        details_text = f"""
📋 **{task['title']}**

📝 Описание: {task['description'] or 'Не указано'}
🎯 Статус: {status_text}
🔥 Приоритет: {priority_text}{due_date_text}{estimated_hours}{actual_hours}
        """
        
        keyboard = []
        if task['status'] not in ['completed', 'cancelled']:
            status_buttons = []
            if task['status'] != 'in_progress':
                status_buttons.append(
                    InlineKeyboardButton("🔄 В работу", callback_data=f"update_status_{task['id']}_in_progress")
                )
            if task['status'] != 'review':
                status_buttons.append(
                    InlineKeyboardButton("👀 На проверку", callback_data=f"update_status_{task['id']}_review")
                )
            if task['status'] != 'completed':
                status_buttons.append(
                    InlineKeyboardButton("✅ Завершить", callback_data=f"update_status_{task['id']}_completed")
                )
            
            if status_buttons:
                keyboard.append(status_buttons)
        
        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None
        await query.edit_message_text(details_text, reply_markup=reply_markup, parse_mode='Markdown')
    
    async def update_task_status(self, query, task_id: str, new_status: str, telegram_username: str):
        """Обновить статус задачи"""
        try:
            user_response = supabase.table('profiles').select('id').eq('telegram_username', telegram_username).execute()
            
            if not user_response.data:
                await query.edit_message_text("❌ Пользователь не найден.")
                return
            
            user_id = user_response.data[0]['id']
            task_response = supabase.table('tasks').select('*').eq('id', task_id).eq('assigned_to', user_id).execute()
            
            if not task_response.data:
                await query.edit_message_text("❌ Задача не найдена или у вас нет прав для её изменения.")
                return
            
            update_data = {'status': new_status}
            if new_status == 'completed':
                update_data['completed_at'] = datetime.now().isoformat()
            
            supabase.table('tasks').update(update_data).eq('id', task_id).execute()
            
            status_text = {
                'in_progress': '🔄 В работе',
                'review': '👀 На проверке',
                'completed': '✅ Выполнено'
            }.get(new_status, new_status)
            
            await query.edit_message_text(f"✅ Статус задачи изменен на: {status_text}")
            
        except Exception as e:
            logger.error(f"Error updating task status: {e}")
            await query.edit_message_text("❌ Ошибка при обновлении статуса задачи.")
    
    def run(self):
        """Запустить бота"""
        logger.info("Запуск Telegram бота...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)

def main():
    """Главная функция"""
    bot = TaskBot()
    bot.run()

if __name__ == '__main__':
    main()
