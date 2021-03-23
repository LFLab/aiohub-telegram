import re
from os import environ
from asyncio import CancelledError, Event, ensure_future, gather, sleep
from collections.abc import Mapping

from aiogram import Bot
from aiohubot import Adapter, TextMessage, CatchAllMessage

__version__ = '0.1.0'
UNSUPPORTED_FIELDS = ("inline_query", "chosen_inline_result", "callback_query",
                      "shipping_query", "pre_checkout_query",
                      "poll", "poll_answer", "my_chat_member", "chat_member")


class Telegram(Adapter):

    def __init__(self, robot):
        super().__init__(robot)
        self.bot = self.stream = self._offset = None
        self._polling = Event()
        self.api_token = environ.get("HUBOT_TELEGRAM_TOKEN", "")
        self.interval = environ.get("HUBOT_TELEGRAM_INTERVAL", 0.5)
        # TODO: support webhook

    async def send(self, envelope, *strings):
        msg, user = envelope['message'], envelope['user']
        if hasattr(msg, 'origin'):
            msg.origin.answer("\n".join(strings))
        else:
            self.robot.logger.warning("Not support, use raw bot directly.")

    async def reply(self, envelope, *strings):
        msg, user = envelope['message'], envelope['user']
        if hasattr(msg, 'origin'):
            msg.origin.reply("\n".join(strings))
        else:
            self.robot.logger.warning("Not support, use raw bot directly.")

    async def run(self):
        if not self.api_token:
            err_msg = "environment `HUBOT_TELEGRAM_TOKEN` is required."
            raise AttributeError(err_msg)

        self.bot = Bot(self.api_token, relax=self.interval)
        Bot.set_current(self.bot)
        me = await self.bot.get_me()
        self.robot.logger.info("Connected to Telegram as Bot"
                               f" {me.first_name}(@{me.username})")

        if me.username.lower() != self.robot.name.lower():
            msg = (f"Inconsistent bot name found: {me.username} from Telegram,"
                   f" {self.robot.name} from Hubot."
                   "\nIt will run into problem when using @mention.")
            self.robot.logger.warning(msg)

        self._polling.set()
        self.stream = ensure_future(self._start_polling())
        self.emit("connected")

    async def _start_polling(self, timeout=20, reset_webhook=True):
        if reset_webhook:
            await self.bot.delete_webhook()

        self.robot.logger.info("Telegram: Start polling...")
        while self._polling.is_set():
            try:
                with self.bot.request_timeout(timeout):
                    updates = await self.bot.get_updates()
            except CancelledError:
                self.emit("disconnected")
                self.robot.logger.debug("Telegram: Polling Received Cancellation.")
                self._polling.clear()
            except Exception as e:
                self.robot.logger.exception(f"Telegram: client error - {e!r}")
                self.emit("clientError", e)
                await sleep(self.interval * 10)
            else:
                if updates:
                    self._offset = updates[-1].update_id + 1
                ensure_future(self.handle_updates(*upates))
                await sleep(self.interval)
        self.robot.logger.info("Telegram: Stop polling...")

    async def handle_updates(self, *updates):
        futs = []
        for update in updates:
            self.robot.logger.debug(f"Received update: {update.to_python()}")
            msg = (update.message or update.edited_message
                   or update.channel_post or update.edited_channel_post)
            if msg:
                user = self.robot.brain.user_for_id(**msg.from_user)
                changed = self.diff_user(user, msg.from_user, update=True)
                hubot_msg = self._msg_reformat(msg.text)
                msg_obj = TextMessage(user, hubot_msg, msg.message_id)
                msg_obj.origin = msg
                futs.append(self.receive(msg_obj))
            else:
                futs.append(self._handle_unsupported(update))

        await gather(*futs)

    def diff_user(self, old, new, update=False):
        if isinstance(old, Mapping):
            old = set(old.items())
        else:
            old = set(old)
        if isinstance(new, Mapping):
            new = set(new.items())
        else:
            new = set(new)

        changed = dict(new-old)
        if update and changed:
            new_m = dict(new)
            u = self.robot.brain.data['users'][new_m['id']]
            u.update(changed)

        return changed

    def close(self):
        self.stream.cancel()

    def _handle_unsupported(self, update):
        for name in UNSUPPORTED_FIELDS:
            if update.values.get(name):
                self.robot.logger.debug(f"Unspported field: {name}")
                obj = update.values[name]
                obj.user = obj.values.get('from')
                msg_obj = CatchAllMessage(obj)
                msg_obj.field = name
                return self.receive(msg_obj)
        else:
            self.robot.logger.warning(f"Update with Unknown field.")
            update.user = None
            msg_obj = CatchAllMessage(update)
            msg_obj.field = None
            return self.receive(msg_obj)

    def _msg_reformat(self, msg):
        bot_prefix = f"{self.robot.name}:"
        hubot_msg = re.sub(fr"^@{self.bot.username}(,\\b)",
                           bot_prefix, msg.text, flags=re.I)
        if (not re.match(fr"^{self.robot.name}", hubot_msg, re.I)
            and msg.chat.type == "private"):
            hubot_msg = bot_prefix + hubot_msg
        return hubot_msg


use = Telegram  # to fit the API
