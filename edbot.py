import asyncio
import configparser
import logging
import mimetypes
import signal
from os import path
from shutil import copyfileobj

import discord
import moment
import requests

# Load bot configuration
config = configparser.ConfigParser()
config.read('config.ini')

# Setup Logging
log_level = logging.getLevelName(config['general']['log_level'])
logger = logging.getLogger("EDBot")
logger.setLevel(log_level)
logFormatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Log to Console
console_handler = logging.StreamHandler()
console_handler.setLevel(log_level)
console_handler.setFormatter(logFormatter)

# Log to File
file_handler = logging.FileHandler(config['general']['log_file'])
file_handler.setLevel(log_level)
file_handler.setFormatter(logFormatter)

# Add Log handlers to logger
logger.addHandler(console_handler)
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


# Ready to go
@discord_client.event
async def on_ready():
    logger.info('Logged in as {0}({1})'.format(discord_client.user.name, discord_client.user.id))
    logger.info("READY")


# Listen for new messages
@discord_client.event
async def on_message(message):
    # we do not want the bot to reply to itself so we ignore any messages that it sends
    if message.author == discord_client.user:
        return

    # listen for new messages in the defined gallery channel that have attachments.
    elif message.channel.id == config['discord']['gallery_channel_id'] and message.attachments:
        logger.info("New gallery post by {0}".format(message.author))
        # iterate over attachments in the message
        for attachment in message.attachments:
            logger.info("Image URL: {0}".format(attachment['url']))
            # get the filetype of attachment based on it's filename
            filetype = (mimetypes.guess_type(attachment['filename'])[0]).split("/")[0]

            # if the attachment is an image
            if filetype == 'image':
                # get the attachment
                r = requests.get(attachment['url'], stream=True)
                # if successful
                if r.status_code == 200:
                    # build a filename based on who uploaded it and when
                    filename = "{0}-{1}{2}".format(
                        message.author.name,
                        moment.date(message.timestamp).strftime("%Y-%m-%dT%H.%M.%S"),
                        path.splitext(attachment['filename'])[1]
                    )
                    # save the image
                    with open(path.join(config['general']['gallery_folder'], filename), 'wb') as f:
                        r.raw.decode_content = True
                        copyfileobj(r.raw, f)
    # TODO: Automattically upload to a gallery of CMDR submitted images.


# Create another background loop to automatically post new GALNET Articles
async def galnet_loop():
    # wait for the discord bot to be ready
    await discord_client.wait_until_ready()
    logger.info("Starting GalNet loop")
    galnet_last_modified = ""

    # while the bot is connected and running
    while not discord_client.is_closed:
        # get information about the defined channel
        channel = discord_client.get_channel(config['discord']['news_channel_id'])

        # get galnet articles from api endpoint and load json data
        r = requests.get(config['elite']['galnet_api'])
        data = r.json()

        # extract the date the article was posted and convert it to a datetime object
        latest_post_datetime = moment.utc(data[0]['date'], 'DD MMM YYY')

        # create the embed that contains the article
        embed = discord.Embed(title=data[0]['title'], description=data[0]['content'].replace("<br /><br />  ", "\n\n"))
        embed.set_author(name="Galnet News", url="https://community.elitedangerous.com/en/galnet")
        embed.add_field(name="Post Date", value=data[0]['date'])

        # if this is our first run or there is a new article post the latest article
        if not galnet_last_modified or (galnet_last_modified and galnet_last_modified < latest_post_datetime):
            logger.info("New galnet article found. Posting to discord.")
            # update the last modified time
            galnet_last_modified = latest_post_datetime
            discord_client.send_message(channel, content=config['discord']['new_news_message'], embed=embed)

        # wait for the defined time before checking again
        await asyncio.sleep(delay=int(config['elite']['check_interval']))


# add the galnet loop to the discord bot
discord_client.loop.create_task(galnet_loop())

# run the bot
if __name__ == "__main__":
    discord_client.run(config['discord']['auth_token'])
