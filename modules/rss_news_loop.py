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
