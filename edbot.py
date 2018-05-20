import asyncio
import configparser
import logging
import signal

import aiohttp
import discord
import feedparser
import moment
from markdownify import markdownify

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


# Listen for new messages
@discord_client.event
async def on_message(message):
    # get config variables
    scrape_gallery = config.getboolean('general', 'scrape_gallery', fallback=False)
    gallery_channel_id = config.get('discord', 'gallery_channel_id', fallback=None)
    gallery_folder = config.get('general', 'gallery_folder')

    # we do not want the bot to reply to itself so we ignore any messages that it sends
    if message.author == discord_client.user:
        return

    # listen for new messages in the defined gallery channel that have attachments.
    elif (
            scrape_gallery
            and message.channel.id == gallery_channel_id
            and message.attachments
    ):
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
                    with open(path.join(gallery_folder, filename), 'wb') as f:
                        r.raw.decode_content = True
                        copyfileobj(r.raw, f)
    # TODO: Automatically upload to a gallery of CMDR submitted images.

# Create a background loop to automatically post new GALNET Articles
async def galnet_loop():
    # wait for the discord bot to be ready
    await discord_client.wait_until_ready()
    logger.info("Starting GalNet loop")
    galnet_last_modified = ""

    # while the bot is connected and running
    while not discord_client.is_closed:
        # get config variables
        news_channel_id = config.get('discord', 'news_channel_id', fallback=None)
        galnet_api = config.get('elite', 'galnet_api', fallback=None)
        news_timestamp_use_ugt = config.getboolean('general', 'news_timestamp_use_ugt', fallback=True)
        timezone = config.get('general', 'timezone', fallback="UTC")
        new_news_message = config.get('discord', 'new_news_message', fallback="@here")
        check_interval = config.getint('general', 'check_interval', fallback=1800)

        # get information about the defined channel
        channel = discord_client.get_channel(news_channel_id)

        if not channel:
            logger.error(
                "Galnet loop enabled but no news channel set or no channel matching {0}, exiting galnet loop.".format(
                    news_channel_id
                )
            )
            return

        if not galnet_api:
            logger.error("No API endpoint set for Galnet News. Exiting galnet loop.")
            return

        # get galnet articles from api endpoint and load json data
        # noinspection PyDeprecation
        async with aiohttp.get(url=galnet_api) as r:
            if r.status == 200:
                data = await r.json()

                # extract the date the article was posted and convert it to a datetime object
                latest_post_datetime = moment.utc(data[0]['date'], 'DD MMM YYYY').locale("UTC")

                # create the embed that contains the article
                embed = discord.Embed(title=data[0]['title'],
                                      description=data[0]['content'].replace("<br /><br />  ", "\n\n"))
                embed.set_author(name="Galnet News", url="https://community.elitedangerous.com/en/galnet")
                if news_timestamp_use_ugt:
                    timestamp = latest_post_datetime.timezone(timezone)
                else:
                    timestamp = latest_post_datetime.subtract(years=1286)
                embed.add_field(name="Post Date", value=timestamp.format('DD MMM YYYY'))

                # if this is our first run or there is a new article post the latest article
                if not galnet_last_modified or (galnet_last_modified and galnet_last_modified < latest_post_datetime):
                    logger.info("New galnet article found. Posting to discord.")
                    # update the last modified time
                    galnet_last_modified = latest_post_datetime
                    await discord_client.send_message(channel, content=new_news_message, embed=embed)
            else:
                logger.error("Failed to get galnet news articles.")

        # wait for the defined time before checking again
        await asyncio.sleep(delay=check_interval)


# Create another background loop to automatically post new RSS Articles
async def rss_news_loop():
    # wait for the discord bot to be ready
    await discord_client.wait_until_ready()
    logger.info("Starting RSS News loop")
    rss_last_modified = ""
    rss_etag = ""

    # while the bot is connected and running
    while not discord_client.is_closed:
        # get config variables
        news_channel_id = config.get('discord', 'news_channel_id', fallback=None)
        rss_url = config.get('news', 'rss_url', fallback=None)
        news_timestamp_use_ugt = config.getboolean('general', 'news_timestamp_use_ugt', fallback=True)
        timezone = config.get('general', 'timezone', fallback="UTC")
        new_news_message = config.get('discord', 'new_news_message', fallback="@here")
        check_interval = config.getint('general', 'check_interval', fallback=1800)

        # get information about the defined channel
        channel = discord_client.get_channel(news_channel_id)

        if not channel:
            logger.error("RSS News loop enabled but no news channel set, exiting RSS News loop.")
            return

        if not rss_url:
            logger.error("News feed URL not set, exiting RSS news loop")
            return

        # get news articles from rss feed
        feed = feedparser.parse(rss_url)

        # If we parse successfully then post the latest article
        if (
                (feed['status'] == 200
                 or (
                (feed['status'] >= 301 and feed['status'] <= 304)
                or (feed['status'] >= 307 and feed['status'] <= 308)
                 ))
                and not feed['bozo']
        ):
            # extract the date the article was posted and convert it to a datetime object
            latest_post_datetime = moment.date(feed['updated'])

            # create the embed that contains the article
            embed = discord.Embed(
                title=feed['entries'][0]['title'],
                description=markdownify(feed['entries'][0]['content'][0]['value'])
            )
            embed.set_author(name="{0} News".format(feed['feed']['title']), url=feed['feed']['links'][1]['href'])
            if news_timestamp_use_ugt:
                timestamp = latest_post_datetime.timezone("UTC").add(years=1286)
            else:
                timestamp = latest_post_datetime.timezone(timezone)
            embed.add_field(name="Post Date", value=timestamp.format('DD MMM YYYY'))
            embed.add_field(name='Author', value=feed['entries'][0]['author'])
            embed.add_field(name="Permalink", value=feed['entries'][0]['id'])

            # if this is our first run or there is a new article post the latest article
            if (
                    (not rss_last_modified or not rss_etag)
                    or (
                    (rss_last_modified and rss_last_modified < latest_post_datetime)
                    and (rss_etag and not rss_etag == feed['etag'])
            )
            ):
                logger.info("New news article found. Posting to discord.")
                # update the last modified time and etag
                rss_last_modified = latest_post_datetime
                rss_etag = feed['etag']
                await discord_client.send_message(
                    channel,
                    content=new_news_message,
                    embed=embed
                )

        else:
            logger.error("Unable to load feed from {0}".format(rss_url))

        # wait for the defined time before checking again
        await asyncio.sleep(delay=check_interval)


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
