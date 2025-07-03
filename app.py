import asyncio
import re
import random
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright, Page, BrowserContext
from playwright_stealth import stealth_async
from user_agents import parse
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# FastAPI app
app = FastAPI(title="Payment Gateway and E-commerce Detector")

# Pydantic model for response
class DetectionResponse(BaseModel):
    url: str
    technologies: List[str]
    checkout_urls: List[str]
    network_insights: List[Dict[str, str]]
    errors: Optional[List[str]] = None

# Technology detection patterns (from provided document)
TECH_PATTERNS = {
    "Stripe": [
        re.compile(r"js\.stripe\.com", re.IGNORECASE),
        re.compile(r"data-stripe", re.IGNORECASE),
        re.compile(r"Stripe\(", re.IGNORECASE),
        # ... (other Stripe patterns from document)
    ],
    "PayPal": [
        re.compile(r"paypalobjects\.com", re.IGNORECASE),
        re.compile(r"paypal\.Buttons", re.IGNORECASE),
        # ... (other PayPal patterns)
    ],
    # ... (other payment gateways and e-commerce platforms from document)
    "Shopify": [
        re.compile(r"shopify\.com", re.IGNORECASE),
        re.compile(r"data-shopify", re.IGNORECASE),
        re.compile(r"Shopify\.", re.IGNORECASE),
    ],
    "WooCommerce": [
        re.compile(r"woocommerce", re.IGNORECASE),
        re.compile(r"wp-content/plugins/woocommerce", re.IGNORECASE),
        re.compile(r"wc-ajax", re.IGNORECASE),
    ],
    "Cloudflare": [
        re.compile(r"cloudflare\.com", re.IGNORECASE),
        re.compile(r"cf-ray", re.IGNORECASE),
        re.compile(r"__cf_chl", re.IGNORECASE),
    ],
    "reCaptcha": [
        re.compile(r"g-recaptcha", re.IGNORECASE),
        re.compile(r"recaptcha/api\.js", re.IGNORECASE),
        # ... (other CAPTCHA patterns)
    ],
    # ... (other CAPTCHA patterns from document)
}

# Checkout URL patterns
CHECKOUT_PATTERNS = [
    re.compile(r"/(cart|checkout|buy|purchase|subscribe|payment|order)", re.IGNORECASE),
    re.compile(r"shopify\.com/checkout", re.IGNORECASE),
    re.compile(r"woocommerce-checkout", re.IGNORECASE),
    re.compile(r"add-to-cart", re.IGNORECASE),
    re.compile(r"payment", re.IGNORECASE),
]

async def detect_technologies(page: Page, html: str) -> Dict:
    """Detect technologies in HTML and JavaScript globals."""
    detected_tech = []
    
    # Scan HTML for patterns
    for tech, patterns in TECH_PATTERNS.items():
        if any(p.search(html) for p in patterns):
            detected_tech.append(tech)
    
    # Check JavaScript globals
    js_globals = await page.evaluate("""
        () => {
            return {
                hasStripe: typeof Stripe !== 'undefined',
                hasPayPal: typeof paypal !== 'undefined',
                hasRazorpay: typeof Razorpay !== 'undefined',
                hasBraintree: typeof braintree !== 'undefined',
                hasAdyen: typeof AdyenCheckout !== 'undefined',
                hasAuthorizeNet: typeof Accept !== 'undefined',
                hasSquare: typeof Square !== 'undefined',
                hasKlarna: typeof Klarna !== 'undefined',
                hasCheckoutCom: typeof Checkout !== 'undefined',
                hasPaytm: typeof Paytm !== 'undefined',
                hasShopifyPayments: typeof Shopify !== 'undefined',
                hasWorldpay: typeof Worldpay !== 'undefined',
                has2Checkout: typeof TwoCheckout !== 'undefined',
                hasAmazonPay: typeof amazon !== 'undefined',
                hasApplePay: typeof ApplePaySession !== 'undefined',
                hasGooglePay: typeof google?.payments?.api !== 'undefined',
                hasMollie: typeof Mollie !== 'undefined',
                hasOpayo: typeof Opayo !== 'undefined',
                hasPaddle: typeof Paddle !== 'undefined',
                hasShopify: typeof Shopify !== 'undefined',
            };
        }
    """)
    
    for key, value in js_globals.items():
        if value:
            tech_name = key.replace("has", "")
            if tech_name not in detected_tech:
                detected_tech.append(tech_name)
    
    return detected_tech

async def find_checkout_urls(page: Page, base_url: str, html: str) -> List[str]:
    """Find potential checkout URLs via link analysis and network inspection."""
    checkout_urls = set()
    
    # Parse HTML for links
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all(["a", "button", "input"]):
        href = link.get("href") or link.get("action")
        text = link.get_text().lower()
        if href and (any(p.search(href) for p in CHECKOUT_PATTERNS) or 
                     any(keyword in text for keyword in ["checkout", "buy", "cart", "subscribe", "pricing"])):
            full_url = urljoin(base_url, href)
            checkout_urls.add(full_url)
    
    # Network inspection for checkout-related requests
    network_requests = []
    def capture_request(request):
        network_requests.append({"url": request.url, "method": request.method})
    
    page.on("request", capture_request)
    
    # Simulate clicks on potential checkout links
    links = await page.locator("a, button, input[type='submit']").all()
    for link in links:
        text = (await link.inner_text()).lower()
        if text and re.search(r"pricing|buy|subscribe|checkout|cart", text, re.IGNORECASE):
            try:
                await link.click(timeout=5000)
                await page.wait_for_timeout(random.randint(300, 1000))
            except Exception as e:
                logger.error(f"Error clicking link {text}: {str(e)}")
    
    # Analyze network requests
    for req in network_requests:
        if any(p.search(req["url"]) for p in CHECKOUT_PATTERNS):
            checkout_urls.add(req["url"])
    
    return list(checkout_urls), network_requests

async def scan_url(url: str) -> Dict:
    """Scan a single URL for technologies and checkout URLs."""
    errors = []
    technologies = []
    checkout_urls = []
    network_insights = []
    
    async with async_playwright() as p:
        # Connect to Bright Data Browser API (as per your document)
        try:
            logger.info(f"Connecting to Bright Data Browser API")
            browser = await p.chromium.connect_over_cdp(
                "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222"
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                extra_http_headers={
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.5",
                    "Accept-Encoding": "gzip, deflate, br",
                    "Connection": "keep-alive",
                    "Upgrade-Insecure-Requests": "1",
                },
            )
            await stealth_async(context)
            page = await context.new_page()
            
            # Apply canvas fingerprinting protection
            await page.evaluate("""
                () => {
                    const originalGetContext = HTMLCanvasElement.prototype.getContext;
                    HTMLCanvasElement.prototype.getContext = function(contextType, contextAttributes) {
                        if (contextType === '2d') {
                            const ctx = originalGetContext.apply(this, arguments);
                            ctx.fillStyle = ctx.fillStyle + String(Math.random()).slice(2, 8);
                            return ctx;
                        }
                        return originalGetContext.apply(this, arguments);
                    };
                }
            """)
            
            # Navigate to URL
            logger.info(f"Navigating to {url}")
            try:
                response = await page.goto(url, timeout=45000, wait_until="networkidle")
                if not response or response.status >= 400:
                    errors.append(f"Failed to load URL: {response.status if response else 'No response'}")
                    return {"url": url, "technologies": [], "checkout_urls": [], "network_insights": [], "errors": errors}
            except Exception as e:
                errors.append(f"Navigation error: {str(e)}")
                return {"url": url, "technologies": [], "checkout_urls": [], "network_insights": [], "errors": errors}
            
            # Simulate human behavior
            logger.info("Simulating human-like interactions")
            await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
            await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await page.wait_for_timeout(random.randint(500, 1500))
            
            # Get page content
            html = await page.content()
            
            # Detect technologies
            technologies = await detect_technologies(page, html)
            
            # Find checkout URLs
            checkout_urls, network_insights = await find_checkout_urls(page, url, html)
            
            await context.close()
            await browser.close()
        
        except Exception as e:
            errors.append(f"Browser error: {str(e)}")
    
    return {
        "url": url,
        "technologies": technologies,
        "checkout_urls": checkout_urls,
        "network_insights": network_insights,
        "errors": errors if errors else None
    }

@app.get("/gatecheck/", response_model=DetectionResponse)
async def gatecheck(url: str):
    """API endpoint to detect payment gateways, e-commerce platforms, and checkout URLs."""
    # Validate URL
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL provided")
    
    # Run detection
    result = await scan_url(url)
    return DetectionResponse(**result)

# Run the FastAPI server
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
