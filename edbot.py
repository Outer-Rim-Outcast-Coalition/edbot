import configparser
import logging
import signal

import discord

from modules.galnet_loop import galnet_loop
from modules.rss_news_loop import rss_news_loop

# Load bot configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Logging
log_level = logging.getLevelName(config.get('general', 'log_level', fallback="INFO"))
logger = logging.getLogger("EDBot")
logger.setLevel(log_level)
logFormatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Log to Console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(logFormatter)
logger.addHandler(console_handler)
# Log to File
logfile = config.get('general', 'log_file', fallback=None)
if logfile:
    file_handler = logging.FileHandler(logfile)
    file_handler.setLevel(log_level)
    file_handler.setFormatter(logFormatter)
    logger.addHandler(file_handler)


# Catch signals and shutdown cleanly
def signal_handler(sig, frame):
    logger.info('Caught signal', sig)
    if sig == signal.SIGTERM or sig == signal.SIGINT:
        logger.info("Exiting")
        discord_client.close()


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

# Initialize discord client
discord_client = discord.Client()

if not config.get('discord', 'auth_token', fallback=None):
    logger.fatal("Discord auth token not set. Please configure edbot.")
    exit(1)

# Ready to go
@discord_client.event
async def on_ready():
    logger.info('Logged in as {0}({1})'.format(discord_client.user.name, discord_client.user.id))
    logger.info("READY")


# add the galnet loop and news loop to the discord bot if enabled
if config.getboolean('general', 'post_galnet_news', fallback=False):
    logger.info("Enabling GALNET News loop")
    discord_client.loop.create_task(galnet_loop())
else:
    logger.info("Galnet News loop not enabled")
if config.getboolean('general', 'post_website_news', fallback=False):
    logger.info("Enabling RSS News loop")
    discord_client.loop.create_task(rss_news_loop())
else:
    logger.info("RSS News loop not enabled")

# run the bot
if __name__ == "__main__":
    discord_client.run(config.get('discord', 'auth_token'))
