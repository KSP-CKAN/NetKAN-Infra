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
        self.webhook.send(self.format(record))


def setup_log_handler():
    # Set up Discord logger so we can see errors
    discord_webhook_id = os.environ.get('DISCORD_WEBHOOK_ID')
    discord_webhook_token = os.environ.get('DISCORD_WEBHOOK_TOKEN')
    if discord_webhook_id and discord_webhook_token:
        handler = DiscordLogHandler(discord_webhook_id, discord_webhook_token)
        handler.setLevel(logging.ERROR)
        logging.getLogger('').addHandler(handler)
        return True
    return False
