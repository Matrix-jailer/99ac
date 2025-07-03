import re
import asyncio
import logging
import random
from typing import List, Dict
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

from detectors import TECH_PATTERNS, detect_technologies_from_text

# --- CONFIG ---
BRIGHT_DATA_CDP = "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("gatecheck")

# --- FastAPI Init ---
app = FastAPI()


# --- Models ---
class DetectionResponse(BaseModel):
    url: str
    found: Dict[str, List[str]]


# --- Core Logic ---
async def fetch_and_analyze(url: str) -> Dict:
    async with async_playwright() as p:
        browser = await p.chromium.connect_over_cdp(BRIGHT_DATA_CDP)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36",
            extra_http_headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
            }
        )
        await stealth_async(context)
        page = await context.new_page()

        await page.evaluate("""
            () => {
                const original = HTMLCanvasElement.prototype.getContext;
                HTMLCanvasElement.prototype.getContext = function(type) {
                    if (type === '2d') {
                        const ctx = original.apply(this, arguments);
                        ctx.fillStyle = ctx.fillStyle + String(Math.random()).slice(2, 8);
                        return ctx;
                    }
                    return original.apply(this, arguments);
                };
            }
        """)

        logger.info(f"Loading page: {url}")
        try:
            resp = await page.goto(url, wait_until="networkidle", timeout=45000)
            if not resp or resp.status >= 400:
                raise Exception(f"Bad status: {resp.status if resp else 'none'}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to load URL: {str(e)}")

        await page.mouse.move(random.randint(100, 500), random.randint(100, 300))
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(random.uniform(0.5, 1.2))

        logger.info("Clicking buttons or links with payment hints...")
        for el in await page.locator("a, button, input[type='submit']").all():
            try:
                text = await el.inner_text()
                if text and re.search(r"checkout|buy|pricing|subscribe|pay", text, re.I):
                    await el.click(timeout=4000)
                    await asyncio.sleep(random.uniform(0.4, 1.0))
                    break
            except Exception:
                continue

        logger.info("Scraping content...")
        content = await page.content()
        js_globals = await page.evaluate("""
            () => {
                return {
                    Stripe: typeof Stripe !== 'undefined',
                    PayPal: typeof paypal !== 'undefined',
                    Razorpay: typeof Razorpay !== 'undefined',
                    Braintree: typeof braintree !== 'undefined',
                    Adyen: typeof AdyenCheckout !== 'undefined',
                    AuthorizeNet: typeof Accept !== 'undefined',
                    Square: typeof Square !== 'undefined',
                    Klarna: typeof Klarna !== 'undefined',
                    CheckoutCom: typeof Checkout !== 'undefined',
                    Paytm: typeof Paytm !== 'undefined',
                    ShopifyPayments: typeof Shopify !== 'undefined',
                    Worldpay: typeof Worldpay !== 'undefined',
                    2Checkout: typeof TwoCheckout !== 'undefined',
                    AmazonPay: typeof amazon !== 'undefined',
                    ApplePay: typeof ApplePaySession !== 'undefined',
                    GooglePay: typeof google?.payments?.api !== 'undefined',
                    Mollie: typeof Mollie !== 'undefined',
                    Opayo: typeof Opayo !== 'undefined',
                    Paddle: typeof Paddle !== 'undefined',
                    Shopify: typeof Shopify !== 'undefined',
                };
            }
        """)

        network_data = []
        for req in page.context.requests:
            try:
                r_url = req.url
                r_headers = req.headers
                r_body = await req.post_data()
                if any(re.search(pat, r_url + str(r_headers) + str(r_body or ''), re.I)
                       for patterns in TECH_PATTERNS.values() for pat in patterns):
                    network_data.append(f"{r_url}\n{r_headers}\n{r_body}")
            except:
                pass

        logger.info("Analyzing fingerprints...")
        found = detect_technologies_from_text(
            html=content,
            js_globals=js_globals,
            network_snippets=network_data
        )

        return {"url": url, "found": found}


# --- Endpoint ---
@app.get("/gatecheck/", response_model=DetectionResponse)
async def gatecheck(url: str):
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if not parsed.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL")
    return await fetch_and_analyze(url)
