# Discord Jukebox
A very basic music bot built with Python 3, ffmpeg and yt-dlp to allow a user to play online audio in a Discord channel. This is not intended for production use but should work fine for a small community or set of communities. The bot can support playing audio in multiple Discord servers (guilds) at once.

## Commands
The default prefix for this bot is `!`. The commands available are:

- **!play** - Play an item
- **!skip** - Skip the current item in the queue
- **!queue** - View all items in the queue
- **!stop** - Stop playing, clear the queue and disconnect
- **!pause** - Pause currently playing track
- **!resume** - Resume currently playing track

## How to Configure
- Clone this repository
- Get a Discord Bot Token ([tutorial](https://docs.discord.com/developers/quick-start/getting-started#fetching-your-credentials))
    - Ensure the bot has Message Content Intent enabled.
- Copy `.env.example` to `.env`
    - Replace the `DISCORD_TOKEN` value with your bot token
    - Replace the `BOT_PREFIX` value with the prefix for commands you wish the bot to use.
- Configure a virtual environment ([tutorial](https://www.w3schools.com/python/python_virtualenv.asp)) and run `pip install -r requirements.txt`
- Run the bot with `python bot.py`