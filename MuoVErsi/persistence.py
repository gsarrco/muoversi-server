import json
import logging
import os
import sqlite3
from typing import Optional, Dict

from telegram import Bot
from telegram.ext import BasePersistence, PersistenceInput
from telegram.ext._utils.types import BD, CD, UD, CDCData, ConversationKey, ConversationDict

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)


class SQLitePersistence(BasePersistence):
    def __init__(self):
        current_dir = os.path.abspath(os.path.dirname(__file__))
        parent_dir = os.path.abspath(current_dir + "/../")
        self.con = sqlite3.connect(os.path.join(parent_dir, 'data.db'))
        self.con.row_factory = sqlite3.Row
        self.con.set_trace_callback(logger.info)
        self.con.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, data TEXT)')
        self.con.execute('CREATE TABLE IF NOT EXISTS chats (chat_id INTEGER PRIMARY KEY, data TEXT)')
        self.con.execute('CREATE TABLE IF NOT EXISTS bot (id INTEGER PRIMARY KEY, data TEXT)')
        self.con.execute('CREATE TABLE IF NOT EXISTS callback_data (id INTEGER PRIMARY KEY, data TEXT)')
        self.con.execute(
            'CREATE TABLE IF NOT EXISTS conversations (name TEXT, key TEXT, state TEXT, UNIQUE (name, key))')
        self.con.execute('DELETE FROM bot')
        self.con.commit()
        store_data = PersistenceInput(bot_data=False, chat_data=False)
        super().__init__(store_data, 10)

    @property
    def update_interval(self) -> float:
        return super().update_interval

    def set_bot(self, bot: Bot) -> None:
        super().set_bot(bot)

    async def get_user_data(self) -> Dict[int, UD]:
        cur = self.con.cursor()
        cur.execute('SELECT user_id, data FROM users')
        return {row['user_id']: json.loads(row['data']) for row in cur.fetchall()}

    async def get_chat_data(self) -> Dict[int, CD]:
        cur = self.con.cursor()
        cur.execute('SELECT chat_id, data FROM chats')
        return {row['chat_id']: json.loads(row['data']) for row in cur.fetchall()}

    async def get_bot_data(self) -> BD:
        cur = self.con.cursor()
        result = cur.execute('SELECT data FROM bot WHERE id = 1').fetchone()
        return json.loads(result['data']) if result else {}

    async def get_callback_data(self) -> Optional[CDCData]:
        cur = self.con.cursor()
        cur.execute('SELECT data FROM callback_data WHERE id = 1')
        return json.loads(cur.fetchone()['data']) if cur.fetchone() else None

    async def get_conversations(self, name: str) -> ConversationDict:
        cur = self.con.cursor()
        cur.execute('SELECT key, state FROM conversations WHERE name = ?', (name,))
        return {tuple(json.loads(row['key'])): json.loads(row['state']) for row in cur.fetchall()}

    async def update_conversation(self, name: str, key: ConversationKey, new_state: Optional[object]) -> None:
        cur = self.con.cursor()
        key = json.dumps(key)
        if new_state is None:
            cur.execute('DELETE FROM conversations WHERE name = ? AND key = ?', (name, key))
        else:
            new_state = json.dumps(new_state)
            cur.execute('INSERT OR REPLACE INTO conversations (name, key, state) VALUES (?, ?, ?)',
                        (name, key, new_state))
        self.con.commit()

    async def update_user_data(self, user_id: int, data: UD) -> None:
        cur = self.con.cursor()
        data = json.dumps(data)
        cur.execute('INSERT OR REPLACE INTO users (user_id, data) VALUES (?, ?)', (user_id, data))
        self.con.commit()

    async def update_chat_data(self, chat_id: int, data: CD) -> None:
        cur = self.con.cursor()
        data = json.dumps(data)
        cur.execute('INSERT OR REPLACE INTO chats (chat_id, data) VALUES (?, ?)', (chat_id, data))
        self.con.commit()

    async def update_bot_data(self, data: BD) -> None:
        cur = self.con.cursor()
        data = json.dumps(data)
        cur.execute('INSERT OR REPLACE INTO bot (id, data) VALUES (1, ?)', (data,))
        self.con.commit()

    async def update_callback_data(self, data: CDCData) -> None:
        cur = self.con.cursor()
        data = json.dumps(data)
        cur.execute('INSERT OR REPLACE INTO callback_data (id, data) VALUES (1, ?)', (data,))
        self.con.commit()

    async def drop_chat_data(self, chat_id: int) -> None:
        cur = self.con.cursor()
        cur.execute('DELETE FROM chats WHERE chat_id = ?', (chat_id,))
        self.con.commit()

    async def drop_user_data(self, user_id: int) -> None:
        cur = self.con.cursor()
        cur.execute('DELETE FROM users WHERE user_id = ?', (user_id,))
        self.con.commit()

    async def refresh_user_data(self, user_id: int, user_data: UD) -> None:
        pass

    async def refresh_chat_data(self, chat_id: int, chat_data: CD) -> None:
        pass

    async def refresh_bot_data(self, bot_data: BD) -> None:
        pass

    async def flush(self) -> None:
        logger.info('closing connection to data.db')
        self.con.close()
