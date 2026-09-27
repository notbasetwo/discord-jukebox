### Option A: Cookies file (recommended, works when the bot runs on a server)
1. In your browser, log in to YouTube with the account you want the bot to use.
2. Install a cookie-export extension, e.g. [Get cookies.txt LOCALLY](https://chromewebstore.google.com/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc) (Chrome) or [cookies.txt](https://addons.mozilla.org/en-US/firefox/addon/cookies-txt/) (Firefox).
3. While on `youtube.com`, use the extension to export cookies and save the file as `cookies.txt` in the project folder (this filename is already git-ignored).
4. In your `.env` file, set:
   ```
   COOKIES_FILE=cookies.txt
   ```
5. Restart the bot.

Treat `cookies.txt` like a password — anyone with the file can access your account. Cookies
expire periodically; if playback of sign-in-gated videos stops working, re-export a fresh file.

### Option B: Read cookies directly from a local browser (only if the bot runs on your own machine)
1. Log in to YouTube in a browser installed on the same machine that runs the bot.
2. In your `.env` file, set:
   ```
   COOKIES_FROM_BROWSER=chrome
   ```
   Supported values include `chrome`, `firefox`, `edge`, `brave`, `vivaldi`, `opera`, `safari`,
   optionally followed by a profile, e.g. `firefox:Default`. Do not use this option if the browser
   isn't installed on the bot's machine, or if the bot is running in a container/headless server
   without your browser profile.
3. Restart the bot. Close the browser first if yt-dlp reports the cookie database is locked.
