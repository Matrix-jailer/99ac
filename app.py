import asyncio
import re
import time
import random
import logging
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

# --------------------------- Custom Exception ---------------------------
class StopScanException(Exception):
    """Exception to stop scan when Shopify Payments is detected."""
    pass

# --------------------------- Logging Setup ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --------------------------- Stealth Script ---------------------------
STEALTH_SCRIPT = """
// Hide navigator.webdriver
Object.defineProperty(navigator, 'webdriver', { get: () => false });

// Fake platform and hardware info
Object.defineProperty(navigator, 'platform', { get: () => 'Win32' });
Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 4 });
Object.defineProperty(navigator, 'deviceMemory', { get: () => 8 });
Object.defineProperty(navigator, 'language', { get: () => 'en-US' });
Object.defineProperty(navigator, 'languages', { get: () => ['en-US', 'en'] });

// Fake userAgentData (if supported)
Object.defineProperty(navigator, 'userAgentData', {
  get: () => ({
    brands: [
      { brand: 'Not:A-Brand', version: '99' },
      { brand: 'Chromium', version: '120' },
    ],
    mobile: false,
    platform: 'Windows'
  })
});

// Patch WebGL rendering info
const getParameter = WebGLRenderingContext.prototype.getParameter;
WebGLRenderingContext.prototype.getParameter = function(parameter) {
  if (parameter === 37445) return 'Intel Inc.'; // UNMASKED_VENDOR_WEBGL
  if (parameter === 37446) return 'Intel Iris OpenGL Engine'; // UNMASKED_RENDERER_WEBGL
  return getParameter.call(this, parameter);
};

// Patch AudioContext fingerprinting
const originalGetFloatFrequencyData = AnalyserNode.prototype.getFloatFrequencyData;
AnalyserNode.prototype.getFloatFrequencyData = function() {
  const originalData = new Float32Array(this.frequencyBinCount);
  originalGetFloatFrequencyData.call(this, originalData);
  for (let i = 0; i < originalData.length; i++) {
    originalData[i] = originalData[i] + Math.random() * 0.1;
  }
  return originalData;
};
"""

# --------------------------- Patterns ---------------------------
ALL_PATTERNS = {}  # Placeholder for your patterns

# --------------------------- Crawler Class ---------------------------
class SiteInspector:
    def __init__(self):
        self.visited = set()
        self.results = defaultdict(set)
        self.cloudflare_detected = set()  # Track Cloudflare network requests

    async def handle_cloudflare_challenge(self, page, url):
        """Detect and attempt to resolve Cloudflare challenge pages."""
        try:
            # Detect Cloudflare challenge via page content and network requests
            content = await page.content()
            cloudflare_indicators = [
                r'checking your browser',
                r'challenges\.cloudflare\.com',
                r'cf-challenge',
                r'__cf_chl_',
                r'cf_clearance',
                r'please wait while we verify',
                r'cloudflare',
                r'cdn-cgi/challenge-platform'
            ]
            is_cloudflare_challenge = (
                any(re.search(pattern, content, re.IGNORECASE) for pattern in cloudflare_indicators) or
                any('cdn-cgi' in req for req in self.cloudflare_detected)
            )

            if not is_cloudflare_challenge:
                logger.info(f"No Cloudflare challenge detected at {url}")
                return True  # Proceed with normal page processing

            logger.info(f"Cloudflare challenge detected at {url}. Attempting to resolve...")

            # Wait for potential automatic resolution (Cloudflare JS challenge)
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)  # Extended to 15 seconds
                # Check if challenge is resolved
                new_content = await page.content()
                new_requests = self.cloudflare_detected
                if not (any(re.search(pattern, new_content, re.IGNORECASE) for pattern in cloudflare_indicators) or
                        any('cdn-cgi' in req for req in new_requests)):
                    logger.info(f"Cloudflare challenge resolved automatically at {url}")
                    return True
            except PlaywrightTimeoutError:
                logger.info(f"Timeout waiting for Cloudflare challenge resolution at {url}. Attempting manual interaction...")

            # Simulate human-like interactions to trigger challenge resolution
            try:
                await page.mouse.move(random.randint(100, 600), random.randint(100, 600))
                await page.mouse.click(random.randint(100, 600), random.randint(100, 600))
                await asyncio.sleep(1.5)
                await page.keyboard.press("ArrowDown")
                await asyncio.sleep(1)
                await page.keyboard.press("Tab")
                await asyncio.sleep(1)
                await page.mouse.move(random.randint(200, 800), random.randint(200, 800))
                await asyncio.sleep(2)

                # Check again for resolution
                new_content = await page.content()
                new_requests = self.cloudflare_detected
                if not (any(re.search(pattern, new_content, re.IGNORECASE) for pattern in cloudflare_indicators) or
                        any('cdn-cgi' in req for req in new_requests)):
                    logger.info(f"Cloudflare challenge resolved after interaction at {url}")
                    return True
                else:
                    logger.warning(f"Cloudflare challenge not resolved after interaction at {url}. Proceeding with scan...")
                    return True  # Proceed anyway to avoid getting stuck
            except Exception as e:
                logger.warning(f"Error during Cloudflare challenge interaction at {url}: {e}")
                return True  # Proceed to avoid getting stuck

        except Exception as e:
            logger.warning(f"Error handling Cloudflare challenge at {url}: {e}")
            return True  # Proceed to avoid getting stuck

    async def simulate_human_behavior(self, page):
        """Simulate human-like behavior for 8 seconds (scrolling, clicking)."""
        try:
            logger.info("Simulating human-like behavior for 8 seconds...")
            # Wait for page stability
            try:
                await page.wait_for_load_state("networkidle", timeout=5000)
            except PlaywrightTimeoutError:
                logger.info("No navigation detected or timeout waiting for network idle.")

            # Scroll down
            await page.mouse.move(random.randint(100, 300), random.randint(100, 300))
            await page.keyboard.press("Tab")
            await asyncio.sleep(2)
            # Scroll up slightly
            await page.mouse.move(random.randint(120, 500), random.randint(120, 500))
            await page.keyboard.press("ArrowDown")
            await asyncio.sleep(2)

            # Try to dismiss cookie/consent overlays
            consent_selectors = [
                'button[class*="cookie"], button[class*="consent"], button[class*="accept"], button[class*="agree"]',
                'a[class*="cookie"], a[class*="consent"], a[class*="accept"], a[class*="agree"]',
                'div[class*="cookie"], div[class*="consent"]'
            ]
            for selector in consent_selectors:
                try:
                    buttons = await page.query_selector_all(selector)
                    for button in buttons[:1]:
                        if await button.is_visible() and await button.is_enabled():
                            await button.evaluate("el => el.click()")  # JavaScript click
                            logger.info("Clicked consent button to dismiss overlay.")
                            await asyncio.sleep(1)
                            break
                    else:
                        continue
                    break
                except Exception as e:
                    logger.info(f"Skipping consent button click for selector '{selector}' due to error: {e}")
            else:
                logger.info("No consent buttons clicked; none found or all failed.")

            # Click a non-critical element (div, span)
            try:
                await page.wait_for_load_state("domcontentloaded", timeout=3000)
                elements = await page.query_selector_all("div, span")
                for element in elements[:1]:
                    if await element.is_visible() and await element.is_enabled():
                        await element.evaluate("el => el.click()")  # JavaScript click
                        logger.info("Clicked on visible element.")
                        break
                else:
                    logger.info("No visible elements found for click.")
            except Exception as e:
                logger.info(f"Skipping click due to error: {e}")

            await asyncio.sleep(4)  # Total 8 seconds
            logger.info("Human-like behavior simulation complete.")
        except Exception as e:
            logger.warning(f"Error during human-like behavior: {e}")

    async def analyze_page_content(self, page, url):
        """Analyze all patterns in HTML content, specific tags, Shadow DOM, and iframes."""
        try:
            # Full HTML content
            content = await page.content()
            for category, patterns in ALL_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(content):
                        self.results[category].add(url)
                        logger.info(f"[{category}] Match in HTML content: {url}")
                        if category == "Shopify Payments":
                            raise StopScanException(f"Shopify Payments detected at {url}")

            # Specific tags: <script>, <form>, <iframe>, <input>, <button>
            tags = {
                "script": await page.query_selector_all("script"),
                "form": await page.query_selector_all("form"),
                "iframe": await page.query_selector_all("iframe"),
                "input": await page.query_selector_all("input"),
                "button": await page.query_selector_all("button")
            }
            for tag_name, elements in tags.items():
                for element in elements:
                    try:
                        # Check attributes and inner content
                        attributes = await element.evaluate("el => Object.fromEntries(Object.entries(el.attributes).map(([k, v]) => [k, v.value]))")
                        inner_html = await element.inner_html() if tag_name != "input" else ""
                        for category, patterns in ALL_PATTERNS.items():
                            for pattern in patterns:
                                if any(pattern.search(str(value)) for value in attributes.values()) or pattern.search(inner_html):
                                    self.results[category].add(url)
                                    logger.info(f"[{category}] Match in {tag_name} tag: {url}")
                                    if category == "Shopify Payments":
                                        raise StopScanException(f"Shopify Payments detected in {tag_name} at {url}")
                    except:
                        continue

            # Shadow DOM
            shadow_elements = await page.evaluate("() => Array.from(document.querySelectorAll('*')).filter(el => el.shadowRoot)")
            for shadow in shadow_elements:
                try:
                    shadow_content = await page.evaluate("el => el.shadowRoot.innerHTML", shadow)
                    for category, patterns in ALL_PATTERNS.items():
                        for pattern in patterns:
                            if pattern.search(shadow_content):
                                self.results[category].add(url)
                                logger.info(f"[{category}] Match in Shadow DOM: {url}")
                                if category == "Shopify Payments":
                                    raise StopScanException(f"Shopify Payments detected in Shadow DOM at {url}")
                except:
                    continue

            # Iframe internal content
            for iframe in tags["iframe"]:
                try:
                    frame = await iframe.content_frame()
                    if frame:
                        iframe_content = await frame.content()
                        for category, patterns in ALL_PATTERNS.items():
                            for pattern in patterns:
                                if pattern.search(iframe_content):
                                    self.results[category].add(url)
                                    logger.info(f"[{category}] Match in iframe content: {url}")
                                    if category == "Shopify Payments":
                                        raise StopScanException(f"Shopify Payments detected in iframe at {url}")
                except:
                    continue

        except StopScanException as e:
            logger.info(str(e))
            raise  # Re-raise to stop scan
        except Exception as e:
            logger.warning(f"Error analyzing page content for {url}: {e}")

    async def analyze_network_requests(self, page, url):
        """Analyze all patterns in network request URLs."""
        async def on_request(request):
            try:
                request_url = request.url
                self.cloudflare_detected.add(request_url)  # Track all network requests for Cloudflare detection
                for category, patterns in ALL_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.search(request_url):
                            self.results[category].add(request_url)
                            logger.info(f"[{category}] Match in network request: {request_url}")
                            if category == "Shopify Payments":
                                raise StopScanException(f"Shopify Payments detected in network request: {request_url}")
            except StopScanException as e:
                logger.info(str(e))
                raise  # Re-raise to stop scan
            except Exception as e:
                logger.warning(f"Error processing request {request.url}: {e}")

        page.on("request", on_request)

    async def extract_internal_links(self, page, base_url):
        """Extract internal links from the page (Depth 1, same domain)."""
        try:
            links = await page.query_selector_all("a")
        except Exception as e:
            logger.warning(f"[Selector Error] Skipping link extraction for {base_url}: {e}")
            return []

        parsed_base = urlparse(base_url)
        hrefs = set()

        for link in links:
            try:
                href = await link.get_attribute("href")
                if href:
                    full_url = urljoin(base_url, href)
                    parsed = urlparse(full_url)
                    if parsed.netloc == parsed_base.netloc and full_url not in self.visited:
                        hrefs.add(full_url)
            except:
                continue

        return list(hrefs)[:5]  # Limit to 5 to avoid rate limits

    async def visit(self, browser, url, depth=0):
        """Visit a URL, simulate human behavior, and analyze for all patterns."""
        if url in self.visited or depth > 1:
            return
        self.visited.add(url)

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()
        await page.mouse.move(random.randint(100, 300), random.randint(100, 300))
        await page.keyboard.press("ArrowDown")
        await self.analyze_network_requests(page, url)

        try:
            logger.info(f"[Depth {depth}] Visiting: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            # Handle Cloudflare challenge before proceeding
            if not await self.handle_cloudflare_challenge(page, url):
                logger.info(f"Skipping further processing due to unresolved Cloudflare challenge at {url}")
                return
            await self.simulate_human_behavior(page)  # Simulate human behavior for 8 seconds
            await self.analyze_page_content(page, url)  # Analyze page content

            # Extract internal links for Depth 1
            if depth == 0:
                links = await self.extract_internal_links(page, url)
                # Process links concurrently with small sleep intervals
                tasks = [self.visit(browser, link, depth + 1) for link in links]
                for i in range(0, len(tasks), 2):  # Process in batches of 2
                    batch = tasks[i:i+2]
                    await asyncio.gather(*batch)
                    await asyncio.sleep(1)  # Small sleep to avoid bot detection
        except StopScanException:
            raise  # Re-raise to stop scan
        except PlaywrightTimeoutError:
            logger.warning(f"[Timeout] {url}")
        except Exception as e:
            logger.warning(f"[Error] {url}: {e}")
        finally:
            await context.close()

    async def run(self, start_url, timeout=None):
        """Run the inspector on the start URL and its Depth 1 links with optional timeout."""
        start = time.time()
        async with async_playwright() as p:
            try:
                browser = await p.chromium.launch(headless=True)  # Use local Chromium browser
                if timeout:
                    await asyncio.wait_for(self.visit(browser, start_url), timeout=timeout)
                else:
                    await self.visit(browser, start_url)
                await browser.close()
            except StopScanException:
                pass  # Stop scan gracefully
            except asyncio.TimeoutError:
                logger.info(f"Scan stopped due to timeout after {timeout} seconds")
            except Exception as e:
                logger.error(f"Failed to launch browser: {e}")

        # Format output as requested
        gateways = {cat for cat in self.results if cat in [
            "stripe", "paypal", "braintree", "adyen", "authorize.net", "square", "klarna",
            "checkout.com", "razorpay", "paytm", "Shopify Payments", "worldpay", "2checkout",
            "Amazon Pay", "Apple Pay", "Google Pay", "mollie", "opayo", "paddle"
        ]}
        captchas = {cat for cat in self.results if cat in [
            "reCaptcha", "hCaptcha", "Turnstile", "Arkose Labs", "GeeTest", "BotDetect",
            "KeyCAPTCHA", "Anti Bot Detection", "Captcha"
        ]}
        cloudflare = "Cloudflare" in self.results
        three_d_secure = "3D Secure" in self.results
        platforms = {cat for cat in self.results if cat in [
            "Shopify", "WooCommerce", "Magento", "Wix", "Squarespace", "PrestaShop", "BigCommerce"
        ]}

        return {
            "URL": start_url,
            "Gateway": ", ".join(gateways) if gateways else "None",
            "Captcha": ", ".join(captchas) if captchas else "None",
            "Cloudflare": "Found" if cloudflare else "Not Found",
            "3D Secure": "3D Secure" if three_d_secure else "None",
            "Platform": ", ".join(platforms) if platforms else "None",
            "Time Taken": f"{time.time() - start:.2f} seconds"
        }

# --------------------------- FastAPI Setup ---------------------------
app = FastAPI()

class ScanRequest(BaseModel):
    url: str
    timeout: float | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Ensure Playwright is properly initialized and cleaned up."""
    async with async_playwright() as p:
        yield

app = FastAPI(lifespan=lifespan)

@app.get("/gate/{url:path}")
async def scan_site(url: str, timeout: float | None = None):
    """API endpoint to scan a website for payment gateways, captchas, and platforms."""
    try:
        # Normalize URL
        if not url.startswith("http"):
            url = "https://" + url
        parsed_url = urlparse(url)
        if not parsed_url.scheme or not parsed_url.netloc:
            raise HTTPException(status_code=400, detail="Invalid URL format")

        # Run the inspector
        inspector = SiteInspector()
        result = await inspector.run(url, timeout)

        return result
    except Exception as e:
        logger.error(f"API Error: {e}")
        raise HTTPException(status_code=500, detail=f"Error processing scan: {str(e)}")

# --------------------------- Entrypoint ---------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
