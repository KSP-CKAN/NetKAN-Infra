import os
import logging
import discord


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
