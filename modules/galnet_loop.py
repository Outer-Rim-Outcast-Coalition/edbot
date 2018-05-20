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
