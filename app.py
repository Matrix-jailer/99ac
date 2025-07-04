import asyncio
import re
import time
import logging
from urllib.parse import urlparse, urljoin
from collections import defaultdict
from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeoutError
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, HttpUrl
import uvicorn

# --------------------------- Logging Setup ---------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# --------------------------- CDP Proxy (Bright Data) ---------------------------
CDP_URL = "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222"

# --------------------------- Stealth Script ---------------------------
STEALTH_SCRIPT = """
() => {
    Object.defineProperty(navigator, 'webdriver', {get: () => false});
    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3]});
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function() {
        const ctx = getContext.call(this, ...arguments);
        return ctx;
    };
}
"""

# --------------------------- Patterns ---------------------------
ALL_PATTERNS = {
    # Payment Gateways
    "stripe": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'stripe\.com', r'api\.stripe\.com/v1', r'js\.stripe\.com', r'stripe\.js', r'stripe\.min\.js',
        r'client_secret', r'payment_intent', r'data-stripe', r'strip-payment-element',
        r'stripe-elements', r'stripe-checkout', r'hooks\.stripe\.com', r'm\.stripe\.network',
        r'stripe__input', r'stripe-card-element', r'stripe-v3ds', r'confirmCardPayment',
        r'createPaymentMethod', r'stripePublicKey', r'stripe\.handleCardAction',
        r'elements\.create', r'js\.stripe\.com/v3/hcaptcha-invisible', r'js\.stripe\.com/v3',
        r'stripe\.createToken', r'stripe-payment-request', r'stripe__frame',
        r'api\.stripe\.com/v1/payment_methods', r'js\.stripe\.com', r'api\.stripe\.com/v1/tokens',
        r'stripe\.com/docs', r'checkout\.stripe\.com', r'stripe-js', r'stripe-redirect',
        r'stripe-payment', r'stripe\.network', r'stripe-checkout\.js'
    ]],
    "paypal": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'api\.paypal\.com', r'paypal\.com', r'paypal-sdk\.com', r'paypal\.js', r'paypalobjects\.com',
        r'paypal_express_checkout', r'e\.PAYPAL_EXPRESS_CHECKOUT', r'paypal-button', r'paypal-checkout-sdk',
        r'paypal-sdk\.js', r'paypal-smart-button', r'paypal_express_checkout/api', r'paypal-rest-sdk',
        r'paypal-transaction', r'itch\.io/api-transaction/paypal', r'PayPal\.Buttons', r'paypal\.Buttons',
        r'data-paypal-client-id', r'paypal\.com/sdk/js', r'paypal\.Order\.create', r'paypal-checkout-component',
        r'api-m\.paypal\.com', r'paypal-funding', r'paypal-hosted-fields', r'paypal-transaction-id',
        r'paypal\.me', r'paypal\.com/v2/checkout', r'paypal-checkout', r'paypal\.com/api',
        r'sdk\.paypal\.com', r'gotopaypalexpresscheckout'
    ]],
    "braintree": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'api\.braintreegateway\.com/v1', r'braintreepayments\.com', r'js\.braintreegateway\.com',
        r'client_token', r'braintree\.js', r'braintree-hosted-fields', r'braintree-dropin', r'braintree-v3',
        r'braintree-client', r'braintree-data-collector', r'braintree-payment-form', r'braintree-3ds-verify',
        r'client\.create', r'braintree\.min\.js', r'assets\.braintreegateway\.com', r'braintree\.setup',
        r'data-braintree', r'braintree\.tokenize', r'braintree-dropin-ui', r'braintree\.com'
    ]],
    "adyen": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'checkoutshopper-live\.adyen\.com', r'adyen\.com/hpp', r'adyen\.js', r'data-adyen', 'adyen\.com',
        r'adyen-checkout', r'adyen-payment', r'adyen-components', r'adyen-encrypted-data',
        r'adyen-cse', r'adyen-dropin', r'adyen-web-checkout', r'live\.adyen-services\.com',
        r'adyen\.encrypt', r'checkoutshopper-test\.adyen\.com', r'adyen-checkout__component',
        r'adyen\.com/v1', r'adyen-payment-method', r'adyen-action', r'adyen\.min\.js', r'adyen\.com'
    ]],
    "authorize.net": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'authorize\.net/gateway/transact\.dll', r'js\.authorize\.net/v1/Accept\.js', r'js\.authorize\.net', 'authorize\.net',
        r'anet\.js', r'data-authorize', r'authorize-payment', r'apitest\.authorize\.net',
        r'accept\.authorize\.net', r'api\.authorize\.net', r'authorize-hosted-form',
        r'merchantAuthentication', r'data-api-login-id', r'data-client-key', r'Accept\.dispatchData',
        r'api\.authorize\.net/xml/v1', r'accept\.authorize\.net/payment', r'authorize\.net/profile'
    ]],
    "square": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'squareup\.com', r'js\.squarecdn\.com', r'square\.js', r'data-square', r'square-payment-form',
        r'square-checkout-sdk', r'connect\.squareup\.com', r'square\.min\.js', r'squarecdn\.com',
        r'squareupsandbox\.com', r'sandbox\.web\.squarecdn\.com', r'square-payment-flow', r'square\.card',
        r'squareup\.com/payments', r'data-square-application-id', r'square\.createPayment'
    ]],
    "klarna": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'klarna\.com', r'js\.klarna\.com', r'klarna\.js', r'data-klarna', r'klarna-checkout',
        r'klarna-onsite-messaging', r'playground\.klarna\.com', r'klarna-payments', r'klarna\.min\.js',
        r'klarna-order-id', r'klarna-checkout-container', r'klarna-load', r'api\.klarna\.com'
    ]],
    "checkout.com": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'api\.checkout\.com', r'cko\.js', r'data-checkout', r'checkout-sdk', r'checkout-payment',
        r'js\.checkout\.com', r'secure\.checkout\.com', r'checkout\.frames\.js', r'api\.sandbox\.checkout\.com',
        r'cko-payment-token', r'checkout\.init', r'cko-hosted', r'checkout\.com/v2', r'cko-card-token'
    ]],
    "razorpay": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'checkout\.razorpay\.com', r'razorpay\.js', r'data-razorpay', r'razorpay-checkout',
        r'razorpay-payment-api', r'razorpay-sdk', r'razorpay-payment-button', r'razorpay-order-id',
        r'api\.razorpay\.com', r'razorpay\.min\.js', r'payment_box payment_method_razorpay',
        r'razorpay', r'cdn\.razorpay\.com', r'rzp_payment_icon\.svg', r'razorpay\.checkout',
        r'data-razorpay-key', r'razorpay_payment_id', r'checkout\.razorpay\.com/v1', r'razorpay-hosted'
    ]],
    "paytm": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'securegw\.paytm\.in', r'api\.paytm\.com', r'paytm\.js', r'data-paytm', r'paytm-checkout',
        r'paytm-payment-sdk', r'paytm-wallet', r'paytm\.allinonesdk', r'securegw-stage\.paytm\.in',
        r'paytm\.min\.js', r'paytm-transaction-id', r'paytm\.invoke', r'paytm-checkout-js',
        r'data-paytm-order-id'
    ]],
    "Shopify Payments": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'pay\.shopify\.com', r'data-shopify-payments', r'shopify-checkout-sdk', r'shopify-payment-api',
        r'shopify-sdk', r'shopify-express-checkout', r'shopify_payments\.js', r'checkout\.shopify\.com',
        r'shopify-payment-token', r'shopify\.card', r'shopify-checkout-api', r'data-shopify-checkout',
        r'shopify\.com/api'
    ]],
    "worldpay": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'secure\.worldpay\.com', r'worldpay\.js', r'data-worldpay', r'worldpay-checkout',
        r'worldpay-payment-sdk', r'worldpay-secure', r'secure-test\.worldpay\.com', r'worldpay\.min\.js',
        r'worldpay\.token', r'worldpay-payment-form', r'access\.worldpay\.com', r'worldpay-3ds',
        r'data-worldpay-token'
    ]],
    "2checkout": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'www\.2checkout\.com', r'2co\.js', r'data-2checkout', r'2checkout-payment', r'secure\.2co\.com',
        r'2checkout-hosted', r'api\.2checkout\.com', r'2co\.min\.js', r'2checkout\.token', r'2co-checkout',
        r'data-2co-seller-id', r'2checkout\.convertplus', r'secure\.2co\.com/v2'
    ]],
    "Amazon Pay": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'payments\.amazon\.com', r'amazonpay\.js', r'data-amazon-pay', r'amazon-pay-button',
        r'amazon-pay-checkout-sdk', r'amazon-pay-wallet', r'amazon-checkout\.js', r'payments\.amazon\.com/v2',
        r'amazon-pay-token', r'amazon-pay-sdk', r'data-amazon-pay-merchant-id', r'amazon-pay-signin',
        r'amazon-pay-checkout-session'
    ]],
    "Apple Pay": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'apple-pay\.js', r'data-apple-pay', r'apple-pay-button', r'apple-pay-checkout-sdk',
        r'apple-pay-session', r'apple-pay-payment-request', r'ApplePaySession', r'apple-pay-merchant-id',
        r'apple-pay-payment', r'apple-pay-sdk', r'data-apple-pay-token', r'apple-pay-checkout',
        r'apple-pay-domain'
    ]],
    "Google Pay": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'pay\.google\.com', r'googlepay\.js', r'data-google-pay', r'google-pay-button',
        r'google-pay-checkout-sdk', r'google-pay-tokenization', r'payments\.googleapis\.com',
        r'google\.payments\.api', r'google-pay-token', r'google-pay-payment-method',
        r'data-google-pay-merchant-id', r'google-pay-checkout', r'google-pay-sdk'
    ]],
    "mollie": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'api\.mollie\.com', r'mollie\.js', r'data-mollie', r'mollie-checkout', r'mollie-payment-sdk',
        r'mollie-components', r'mollie\.min\.js', r'profile\.mollie\.com', r'mollie-payment-token',
        r'mollie-create-payment', r'data-mollie-profile-id', r'mollie-checkout-form', r'mollie-redirect'
    ]],
    "opayo": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'live\.opayo\.eu', r'opayo\.js', r'data-opayo', r'opoayo-checkout', r'opayo-payment-sdk',
        r'opayo-form', r'test\.opayo\.eu', r'opayo\.min\.js', r'opayo-payment-token', r'opayo-3ds',
        r'data-opayo-merchant-id', r'opayo-hosted', r'opayo\.api'
    ]],
    "paddle": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'checkout\.paddle\.com', r'paddle_button\.js', r'paddle\.js', r'data-paddle',
        r'paddle-checkout-sdk', r'paddle-product-id', r'api\.paddle\.com', r'paddle\.min\.js',
        r'paddle-checkout', r'data-paddle-vendor-id', r'paddle\.Checkout\.open', r'paddle-transaction-id',
        r'paddle-hosted'
    ]],
    "ThreeD": [
        re.compile(r"(three_d_secure|3dsecure|three_d_secure_usage|tdsecure|secure-auth|three_d)", re.IGNORECASE)
    ],
    # Captcha and Anti-Bot Patterns
    "reCaptcha": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'g-recaptcha', r'recaptcha/api\.js', r'data-sitekey', r'nocaptcha',
        r'recaptcha\.net', r'www\.google\.com/recaptcha', r'grecaptcha\.execute',
        r'grecaptcha\.render', r'grecaptcha\.ready', r'recaptcha-token'
    ]],
    "hCaptcha": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'hcaptcha', r'assets\.hcaptcha\.com', r'hcaptcha\.com/1/api\.js',
        r'data-hcaptcha-sitekey', r'js\.stripe\.com/v3/hcaptcha-invisible', r'hcaptcha-invisible', r'hcaptcha\.execute'
    ]],
    "Turnstile": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'turnstile', r'challenges\.cloudflare\.com', r'cf-turnstile-response',
        r'data-sitekey', r'__cf_chl_', r'cf_clearance'
    ]],
    "Arkose Labs": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'arkose-labs', r'funcaptcha', r'client-api\.arkoselabs\.com',
        r'fc-token', r'fc-widget', r'arkose', r'press and hold', r'funcaptcha\.com'
    ]],
    "GeeTest": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'geetest', r'gt_captcha_obj', r'gt\.js', r'geetest_challenge',
        r'geetest_validate', r'geetest_seccode'
    ]],
    "BotDetect": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'botdetectcaptcha', r'BotDetect', r'BDC_CaptchaImage', r'CaptchaCodeTextBox'
    ]],
    "KeyCAPTCHA": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'keycaptcha', r'kc_submit', r'kc__widget', r's_kc_cid'
    ]],
    "Anti Bot Detection": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'fingerprintjs', r'js\.challenge', r'checking your browser',
        r'verify you are human', r'please enable javascript and cookies',
        r'sec-ch-ua-platform'
    ]],
    "Captcha": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'captcha-container', r'captcha-box', r'captcha-frame', r'captcha_input',
        r'id="captcha"', r'class="captcha"', r'iframe.+?captcha',
        r'data-captcha-sitekey'
    ]],
    # E-commerce Platforms
    "Shopify": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'shopify\.com', r'data-shopify'
    ]],
    "WooCommerce": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'woocommerce', r'wp-content/plugins/woocommerce', r'wc-ajax'
    ]],
    # Cloudflare
    "Cloudflare": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'cloudflare\.com', r'cf-ray', r'__cf_chl', r'checking your browser', r'__cfduid', r'cf-request-id', r'js.challenge', r'challenge-platform', r'cf_clearance', r'cdn-cgi'
    ]]
}
# --------------------------- Pydantic Model for Input Validation ---------------------------
class ScanRequest(BaseModel):
    url: HttpUrl
    timeout: int | None = None  # Timeout in seconds, optional

# --------------------------- FastAPI Setup ---------------------------
app = FastAPI(title="Gateway Scanner API")

# --------------------------- Crawler Class ---------------------------
class NetworkInspector:
    def __init__(self):
        self.visited = set()
        self.results = defaultdict(set)

    async def analyze_network_requests(self, page, base_url):
        async def on_request(request):
            try:
                url = request.url
                headers = await request.all_headers()
                response = await request.response()
                body = await response.text() if response else ""
            except:
                body = ""
                headers = {}
                url = request.url

            for category, patterns in ALL_PATTERNS.items():
                for pattern in patterns:
                    if pattern.search(url) or any(pattern.search(str(v)) for v in headers.values()) or pattern.search(body):
                        self.results[category].add(url)
                        logger.info(f"[{category}] Match in: {url}")
        page.on("request", on_request)

    async def extract_internal_links(self, page, base_url):
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

        return list(hrefs)[:5]  # Limit to 5 to avoid BrightData rate limit

    async def visit(self, browser, url, depth=0):
        if url in self.visited or depth > 1:
            return
        self.visited.add(url)

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        await context.add_init_script(STEALTH_SCRIPT)
        page = await context.new_page()
        await self.analyze_network_requests(page, url)

        try:
            logger.info(f"[Depth {depth}] Visiting: {url}")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(4000)
            if depth == 0:
                links = await self.extract_internal_links(page, url)
                for link in links:
                    await self.visit(browser, link, depth + 1)
        except PlaywrightTimeoutError:
            logger.warning(f"[Timeout] {url}")
        except Exception as e:
            logger.warning(f"[Error] {url}: {e}")
        finally:
            await context.close()

    async def run(self, start_url, timeout=None):
        start = time.time()
        async with async_playwright() as p:
            try:
                browser = await p.chromium.connect_over_cdp(CDP_URL)
                if timeout:
                    # Run the visit task with a timeout
                    await asyncio.wait_for(self.visit(browser, start_url), timeout=timeout)
                else:
                    await self.visit(browser, start_url)
                await browser.close()
            except asyncio.TimeoutError:
                logger.info(f"Scan timed out after {timeout} seconds")
            except Exception as e:
                logger.error(f"Failed to launch browser: {e}")

        time_taken = time.time() - start
        # Format results as per user specification
        result = {
            "URL": start_url,
            "Gateway": list(self.results.get("stripe", []) | 
                           self.results.get("paypal", []) | 
                           self.results.get("braintree", []) | 
                           self.results.get("adyen", []) | 
                           self.results.get("authorize.net", []) | 
                           self.results.get("square", []) | 
                           self.results.get("klarna", []) | 
                           self.results.get("checkout.com", []) | 
                           self.results.get("razorpay", []) | 
                           self.results.get("paytm", []) | 
                           self.results.get("Shopify Payments", []) | 
                           self.results.get("worldpay", []) | 
                           self.results.get("2checkout", []) | 
                           self.results.get("Amazon Pay", []) | 
                           self.results.get("Apple Pay", []) | 
                           self.results.get("Google Pay", []) | 
                           self.results.get("mollie", []) | 
                           self.results.get("opayo", []) | 
                           self.results.get("paddle", [])),
            "Captcha": list(self.results.get("reCaptcha", []) | 
                           self.results.get("hCaptcha", []) | 
                           self.results.get("Turnstile", []) | 
                           self.results.get("Arkose Labs", []) | 
                           self.results.get("GeeTest", []) | 
                           self.results.get("BotDetect", []) | 
                           self.results.get("KeyCAPTCHA", []) | 
                           self.results.get("Anti Bot Detection", []) | 
                           self.results.get("Captcha", [])),
            "Cloudflare": list(self.results.get("Cloudflare", [])),
            "3D Secure": list(self.results.get("ThreeD", [])),
            "Time Taken": f"{time_taken:.2f} seconds"
        }
        return result

# --------------------------- API Endpoint ---------------------------
@app.get("/gatecheck/")
async def scan_url(url: str, timeout: int | None = None):
    # Validate URL
    if not url.startswith("http"):
        url = "http://" + url
    try:
        # Validate timeout range (15-1000 seconds)
        if timeout is not None and (timeout < 15 or timeout > 1000):
            raise HTTPException(status_code=400, detail="Timeout must be between 15 and 1000 seconds")
        
        # Run the scanner
        inspector = NetworkInspector()
        result = await inspector.run(url, timeout)
        return result
    except Exception as e:
        logger.error(f"API Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

# --------------------------- Entrypoint ---------------------------
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
