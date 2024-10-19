import os
import sys
import re
import logging
from typing import Iterable, Type, Optional
from types import TracebackType
import discord

# A regex to prevent internetarchive's errors from going to Discord
NOT_IA_PATTERN = re.compile('^(?!.*internetarchive)')


def catch_all(type_: Type[BaseException], value: BaseException, traceback: Optional[TracebackType]) -> None:
    # Log an error for Discord
    logging.error("Uncaught exception:", exc_info=(type_, value, traceback))
    if traceback:
        # Pass to default handler (prints, exits, etc.)
        sys.__excepthook__(type_, value, traceback)


class DiscordLogHandler(logging.Handler):

    def __init__(self, webhook_id: str, webhook_token: str,
                 logger_filter: re.Pattern[str]) -> None:
        super().__init__()
        self.webhook = discord.Webhook.partial(webhook_id, webhook_token,
                                               adapter=discord.RequestsWebhookAdapter())
        self.logger_filter = logger_filter

    def emit(self, record: logging.LogRecord) -> None:
        if self.logger_filter.match(record.name):
            fmt = self.format(record)
            as_code = "\n" in fmt
            for part in self._message_parts(fmt, as_code):
                self.webhook.send(part)

    @staticmethod
    def _message_parts(msg: str, as_code: bool, max_len: int = 2000) -> Iterable[str]:
        if as_code:
            return (f'```{msg[start:start+max_len-6]}```'
                    for start in range(0, len(msg), max_len - 6))
        return (msg[start:start + max_len] for start in range(0, len(msg), max_len))


def setup_log_handler(debug: bool = False) -> bool:
    if not sys.argv[0].endswith('gunicorn'):
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
        )
        logging.debug('Logging started for \'%s\' at log level %s', sys.argv[1], level)

    # Set up Discord logger so we can see errors
    discord_webhook_id = os.environ.get('DISCORD_WEBHOOK_ID')
    discord_webhook_token = os.environ.get('DISCORD_WEBHOOK_TOKEN')
    if discord_webhook_id and discord_webhook_token:
        handler = DiscordLogHandler(discord_webhook_id, discord_webhook_token, NOT_IA_PATTERN)
        handler.setLevel(logging.ERROR)
        logging.getLogger('').addHandler(handler)
        return True
    return False
