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
        r'checkoutshopper-live\.adyen\.com', r'adyen\.com/hpp', r'adyen\.js', r'data-adyen', r'adyen\.com',
        r'adyen-checkout', r'adyen-payment', r'adyen-components', r'adyen-encrypted-data',
        r'adyen-cse', r'adyen-dropin', r'adyen-web-checkout', r'live\.adyen-services\.com',
        r'adyen\.encrypt', r'checkoutshopper-test\.adyen\.com', r'adyen-checkout__component',
        r'adyen\.com/v1', r'adyen-payment-method', r'adyen-action', r'adyen\.min\.js', r'adyen\.com'
    ]],
    "authorize.net": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'authorize\.net/gateway/transact\.dll', r'js\.authorize\.net/v1/Accept\.js', r'js\.authorize\.net', r'authorize\.net',
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
    "3D Secure": [
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
        r'shopify\.com', r'data-shopify', r'hopify-buy\.js', r'cdn\.shopify\.com', r'ShopifyAnalytics'
    ]],
    "WooCommerce": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'woocommerce', r'wp-content/plugins/woocommerce', r'wc-ajax'
    ]],
    "Magento": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'Magento', r'mage/requirejs/mage', r'Magento_', r'mage\.cookies'
    ]],
    "Wix": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'wix\.com', r'wixStores', r'shops\.wixapps\.net'
    ]],
    "Squarespace": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'squarespace\.com', r'SquarespaceCommerce', r'//static\.squarespace\.com'
    ]],
    "PrestaShop": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'PrestaShop', r'blockcart\.js', r'/ps_shoppingcart/'
    ]],
    "BigCommerce": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'bigcommerce\.com', r'stencil-utils', r'cdn\.bcappsvc\.com'
    ]],
    # Cloudflare
    "Cloudflare": [re.compile(pattern, re.IGNORECASE) for pattern in [
        r'cloudflare\.com', r'cf-ray', r'__cf_chl', r'checking your browser', r'__cfduid', r'cf-request-id', r'js.challenge', r'challenge-platform', r'cf_clearance', r'cdn-cgi'
    ]]
}


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
