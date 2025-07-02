import aiohttp
import nodriver as uc
from aiohttp import web
from nodriver import cdp
import asyncio
from typing import TypedDict, Optional
import time
from rich.logging import RichHandler
from rich.console import Console
from rich.theme import Theme
import logging
import os


console = Console(
    theme=Theme(
        {
            "logging.level.error": "bold red",
            "logging.level.warning": "yellow",
            "logging.level.info": "green",
        }
    )
)
logging.basicConfig(
    level="INFO",
    format="%(message)s",
    datefmt="%X",
    handlers=[
        RichHandler(
            rich_tracebacks=True,
            show_level=True,
            show_path=True,
            console=console,
        )
    ],
)
logger: logging.Logger = logging.getLogger(__name__)


class AccessTokenResponse(TypedDict):
    accessToken: str
    accessTokenExpirationTimestampMs: int
    clientId: str
    isAnonymous: bool
    _notes: Optional[str]


class Handler:
    def __init__(self) -> None:
        self.browser: uc.Browser
        self.tab: uc.Tab
        self.session: aiohttp.ClientSession
        self._refresh_task: asyncio.Task
        self.token_response: Optional[AccessTokenResponse] = None

        self.app = web.Application(logger=logger)
        self.app.router.add_get("/token", self.handle_token_request)
        self.app.on_startup.append(self.on_startup)
        self.app.on_cleanup.append(self.on_cleanup)
    
    def get_chrome_executable(self):
        """Get Chrome executable path with fallbacks"""
        chrome_path = os.getenv('CHROME_EXECUTABLE_PATH')
        if chrome_path and os.path.isfile(chrome_path):
            return chrome_path
        
        fallback_paths = [
            '/usr/bin/google-chrome',
            '/usr/bin/google-chrome-stable',
            '/usr/bin/chromium',
            '/usr/bin/chromium-browser'
        ]
        
        for path in fallback_paths:
            if os.path.isfile(path):
                return path
        
        return None    

    def should_refresh_token(self) -> bool:
        if not self.token_response:
            return True
        return (
            time.time() + 60  
            >= self.token_response["accessTokenExpirationTimestampMs"] / 1000
        )

    async def on_startup(self, app: web.Application) -> None:
        chrome_path = self.get_chrome_executable()
        logger.info("Starting the browser executable: %s", chrome_path)
        if not chrome_path:
            raise FileNotFoundError("Chrome executable not found")
    
        self.session = aiohttp.ClientSession(
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/137.0.0.0 Safari/537.36"
                )
            }
        )
        self.browser = await uc.start(
            browser_args=["--headless=true", "--disable-gpu=true", "--no-sandbox=True"] , browser_executable_path=chrome_path
        )
        self.tab = self.browser.main_tab
        self.tab.add_handler(cdp.fetch.RequestPaused, self.request_paused_handler)
        logger.info("Opening URL : https://open.spotify.com/")
        await self.tab.get("https://open.spotify.com/")
        await asyncio.sleep(5)
        logger.info("Spotify ready.")
        self._refresh_task = asyncio.create_task(self._refresh_loop())

    async def on_cleanup(self, _ : web.Application) -> None:
        logger.info("Cleaning up…")
        self._refresh_task.cancel()
        with suppress(asyncio.CancelledError):
            await self._refresh_task
        await self.session.close()
        for tab in self.browser.tabs:
            await tab.close()
        await asyncio.to_thread(self.browser.stop())
        logger.info("Cleanup complete.")

    async def _refresh_loop(self) -> None:
        try:
            while True:
                if self.should_refresh_token():
                    logger.info("Refreshing token…")
                    await self.tab.reload()
                    await asyncio.sleep(20)
                else:
                    logger.info("Token still valid; sleeping 60s…")
                    await asyncio.sleep(60)
        except asyncio.CancelledError:
            logger.info("Refresh loop cancelled.")

    async def request_paused_handler(self, evt: cdp.fetch.RequestPaused) -> None:
        url = evt.request.url
        if "open.spotify.com/api/token" in url:
            async with self.session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if "accessToken" in data:
                        logger.info("Successfully fetched access token : %s" , data)
                        self.token_response = data
                else:        
                    error = await resp.text()
                    logger.error(f"Error fetching token: {error}")        
        else:
            if url.startswith(
                (
                    "https://open.spotifycdn.com/cdn/images/",
                    "https://encore.scdn.co/fonts/",
                )
            ):
                return
            await self.tab.feed_cdp(cdp.fetch.continue_request(evt.request_id))

    async def handle_token_request(self, _: web.Request) -> web.Response:
        if not self.token_response:
            return web.json_response({"error": "no token"}, status=404)
        return web.json_response(self.token_response)


def main():
    handler = Handler()
    web.run_app(handler.app, host=os.getenv("HOST" , "0.0.0.0"), port=int(os.getenv("PORT", 8080)))


if __name__ == "__main__":
    from contextlib import suppress
    main()
