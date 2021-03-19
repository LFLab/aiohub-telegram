from os import environ
from asyncio import CancelledError, Event, ensure_future, sleep

from aiogram import Bot
from aiohubot import Adapter

__version__ = '0.1.0'


class Telegram(Adapter):

    def __init__(self, robot):
        super().__init__(robot)
        self.bot = self.stream = self._offset = None
        self._polling = Event()
        self.api_token = environ.get("HUBOT_TELEGRAM_TOKEN", "")
        self.interval = environ.get("HUBOT_TELEGRAM_INTERVAL", 0.5)
        # TODO: support webhook

    async def send(self, envelope, *strings):
        pass

    async def reply(self, envelope, *strings):
        pass

    def user_from_id(self, id, **options):
        pass

    async def run(self):
        if not self.api_token:
            err_msg = "environment `HUBOT_TELEGRAM_TOKEN` is required."
            raise AttributeError(err_msg)

        self.bot = Bot(self.api_token, relax=self.interval)
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

    async def handle_updates(self, *messages):
        pass

    async def handle_message(self, message):
        pass

    def close(self):
        self.stream.cancel()


use = Telegram  # to fit the API
