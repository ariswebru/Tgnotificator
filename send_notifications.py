
#!/usr/bin/env python3
"""
Скрипт для отправки отложенных уведомлений
Запускается по расписанию (например, каждую минуту)
"""

import os
import asyncio
import aiohttp
import logging
from supabase import create_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SERVICE_ROLE_KEY = os.getenv('SUPABASE_SERVICE_ROLE_KEY')
EDGE_FUNCTION_URL = f"{SUPABASE_URL}/functions/v1/telegram-notifications"

async def send_pending_notifications():
    """Отправить все отложенные уведомления"""
    try:
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {SUPABASE_SERVICE_ROLE_KEY}',
                'Content-Type': 'application/json'
            }
            
            payload = {
                'action': 'send_pending_notifications'
            }
            
            async with session.post(EDGE_FUNCTION_URL, json=payload, headers=headers) as response:
                result = await response.json()
                
                if response.status == 200:
                    logger.info(f"Обработано уведомлений: {result.get('processed', 0)}")
                else:
                    logger.error(f"Ошибка при отправке уведомлений: {result}")
                    
    except Exception as e:
        logger.error(f"Ошибка в send_pending_notifications: {e}")

async def main():
    """Главная функция"""
    if not all([SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY]):
        logger.error("Необходимо установить переменные окружения: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY")
        return
    
    await send_pending_notifications()

if __name__ == '__main__':
    asyncio.run(main())
