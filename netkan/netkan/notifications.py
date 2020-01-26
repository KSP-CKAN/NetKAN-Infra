import os
import sys
import logging
import discord


def catch_all(exception_type, value, stacktrace):
    # Log an error for Discord
    logging.error("Uncaught exception:", exc_info=(exception_type, value, stacktrace))
    # Pass to default handler (prints, exits, etc.)
    sys.__excepthook__(exception_type, value, stacktrace)


class DiscordLogHandler(logging.Handler):

    def __init__(self, webhook_id, webhook_token):
        super().__init__()
        self.webhook = discord.Webhook.partial(webhook_id, webhook_token,
                                               adapter=discord.RequestsWebhookAdapter())

    def emit(self, record):
        fmt = self.format(record)
        as_code = "\n" in fmt
        for part in self._message_parts(fmt, as_code):
            self.webhook.send(part)


    @staticmethod
    def _message_parts(msg, as_code, max_len=2000):
        if as_code:
            return (f'```{msg[start:start+max_len-6]}```'
                    for start in range(0, len(msg), max_len - 6))
        return (msg[start:start+max_len] for start in range(0, len(msg), max_len))


def setup_log_handler(debug=False):
    if not sys.argv[0].endswith('gunicorn'):
        level = logging.DEBUG if debug else logging.INFO
        logging.basicConfig(
            format='[%(asctime)s] [%(levelname)-8s] %(message)s', level=level
        )
        logging.info('Logging started for \'%s\' at log level %s', sys.argv[1], level)

    # Set up Discord logger so we can see errors
    discord_webhook_id = os.environ.get('DISCORD_WEBHOOK_ID')
    discord_webhook_token = os.environ.get('DISCORD_WEBHOOK_TOKEN')
    if discord_webhook_id and discord_webhook_token:
        handler = DiscordLogHandler(discord_webhook_id, discord_webhook_token)
        handler.setLevel(logging.ERROR)
        logging.getLogger('').addHandler(handler)
        return True
    return False
