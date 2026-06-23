import asyncio
import logging
import platform
import traceback

logger = logging.getLogger(__name__)


def _run_playwright_isolated(url: str, timeout: int) -> str | None:
    """Run Playwright in a fully isolated event loop to fix Windows subprocess errors."""
    try:
        if platform.system() == "Windows":
            # Uvicorn uses SelectorEventLoop on Windows, which breaks Playwright's subprocesses.
            # We must use ProactorEventLoop in this isolated thread.
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    except Exception as e:
        with open("pw_error.log", "a") as f:
            f.write(f"Error initializing loop: {e}\n{traceback.format_exc()}\n")
        return None

    async def _do_fetch():
        from playwright.async_api import async_playwright
        browser = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/122.0.0.0 Safari/537.36"
                    ),
                    java_script_enabled=True,
                )
                page = await context.new_page()

                logger.info("Playwright: navigating to %s", url)
                await page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)

                # Give the SPA time to render its content via JS
                await asyncio.sleep(5)

                # Scroll to trigger lazy-loaded content
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await asyncio.sleep(3)

                html = await page.content()
                logger.info("Playwright: got %d chars from %s", len(html), url)

                await browser.close()

                if html and len(html) > 100:
                    return html

                logger.warning("Playwright: HTML too short (%d chars) for %s", len(html), url)
                return html # Return it anyway so we can see what it is instead of pretending it failed

        except Exception as e:
            with open("pw_error.log", "a") as f:
                f.write(f"Error for {url}: {e}\n{traceback.format_exc()}\n")
            logger.error(
                "Playwright fetch failed for %s: %s\n%s",
                url, e, traceback.format_exc()
            )
            if browser:
                try:
                    await browser.close()
                except Exception:
                    pass
            return None

    try:
        return loop.run_until_complete(_do_fetch())
    finally:
        loop.close()


async def fetch_with_playwright(url: str, timeout: int = 60) -> str | None:
    """Fetch a page using Playwright in a background thread with an isolated event loop."""
    try:
        from playwright.async_api import async_playwright  # noqa: F401
    except ImportError as e:
        with open("pw_error.log", "a") as f:
            f.write(f"ImportError: {e}\n{traceback.format_exc()}\n")
        logger.warning("Playwright not installed. Skipping browser fetch.")
        return None

    try:
        return await asyncio.to_thread(_run_playwright_isolated, url, timeout)
    except Exception as e:
        with open("pw_error.log", "a") as f:
            f.write(f"Error in to_thread: {e}\n{traceback.format_exc()}\n")
        return None