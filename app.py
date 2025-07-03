import asyncio
import re
import random
import logging
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from urllib.parse import urlparse, urljoin
from playwright.async_api import async_playwright, Page, BrowserContext, Error
from playwright_stealth import stealth_async
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

# Technology detection patterns (abridged for brevity; use full TECH_PATTERNS from your document)
TECH_PATTERNS = {
    "Stripe": [
        re.compile(r"js\.stripe\.com", re.IGNORECASE),
        re.compile(r"data-stripe", re.IGNORECASE),
        re.compile(r"Stripe\(", re.IGNORECASE),
        re.compile(r"stripe\.js", re.IGNORECASE),
        re.compile(r"stripe\.min\.js", re.IGNORECASE),
        re.compile(r"client_secret", re.IGNORECASE),
        re.compile(r"payment_intent", re.IGNORECASE),
        re.compile(r"stripe-payment-element", re.IGNORECASE),
        re.compile(r"stripe-elements", re.IGNORECASE),
        re.compile(r"stripe-checkout", re.IGNORECASE),
        re.compile(r"stripe__input", re.IGNORECASE),
        re.compile(r"stripe-card-element", re.IGNORECASE),
        re.compile(r"stripe-v3ds", re.IGNORECASE),
        re.compile(r"confirmCardPayment", re.IGNORECASE),
        re.compile(r"createPaymentMethod", re.IGNORECASE),
        re.compile(r"stripePublicKey", re.IGNORECASE),
        re.compile(r"stripe\.handleCardAction", re.IGNORECASE),
        re.compile(r"elements\.create", re.IGNORECASE),
        re.compile(r"js\.stripe\.com/v3/hcaptcha-invisible", re.IGNORECASE),
        re.compile(r"stripe\.createToken", re.IGNORECASE),
        re.compile(r"stripe-payment-request", re.IGNORECASE),
        re.compile(r"stripe__frame", re.IGNORECASE),
        re.compile(r"stripe-checkout\.js", re.IGNORECASE),
        re.compile(r"stripe-payment", re.IGNORECASE),
        re.compile(r"stripe-redirect", re.IGNORECASE),
    ],
    "PayPal": [
        re.compile(r"paypalobjects\.com", re.IGNORECASE),
        re.compile(r"paypal\.Buttons", re.IGNORECASE),
        re.compile(r"data-paypal", re.IGNORECASE),
        re.compile(r"paypal\.js", re.IGNORECASE),
        re.compile(r"paypal-sdk\.js", re.IGNORECASE),
        re.compile(r"paypal-smart-button", re.IGNORECASE),
        re.compile(r"paypal-button", re.IGNORECASE),
        re.compile(r"paypal-checkout-sdk", re.IGNORECASE),
        re.compile(r"paypal-hosted-fields", re.IGNORECASE),
        re.compile(r"paypal-transaction-id", re.IGNORECASE),
        re.compile(r"paypal\.me", re.IGNORECASE),
        re.compile(r"paypal-checkout", re.IGNORECASE),
        re.compile(r"data-paypal-client-id", re.IGNORECASE),
        re.compile(r"paypal\.Order\.create", re.IGNORECASE),
        re.compile(r"paypal-checkout-component", re.IGNORECASE),
        re.compile(r"paypal-funding", re.IGNORECASE),
    ],
    "Razorpay": [
        re.compile(r"checkout\.razorpay\.com", re.IGNORECASE),
        re.compile(r"Razorpay\(", re.IGNORECASE),
        re.compile(r"data-razorpay", re.IGNORECASE),
        re.compile(r"razorpay\.js", re.IGNORECASE),
        re.compile(r"razorpay-checkout", re.IGNORECASE),
        re.compile(r"razorpay-payment-api", re.IGNORECASE),
        re.compile(r"razorpay-sdk", re.IGNORECASE),
        re.compile(r"razorpay-payment-button", re.IGNORECASE),
        re.compile(r"razorpay-order-id", re.IGNORECASE),
        re.compile(r"razorpay\.min\.js", re.IGNORECASE),
        re.compile(r"payment_box payment_method_razorpay", re.IGNORECASE),
        re.compile(r"cdn\.razorpay\.com", re.IGNORECASE),
        re.compile(r"rzp_payment_icon\.svg", re.IGNORECASE),
        re.compile(r"razorpay\.checkout", re.IGNORECASE),
        re.compile(r"data-razorpay-key", re.IGNORECASE),
        re.compile(r"razorpay_payment_id", re.IGNORECASE),
        re.compile(r"razorpay-hosted", re.IGNORECASE),
    ],
    "Braintree": [
        re.compile(r"braintreepayments\.com", re.IGNORECASE),
        re.compile(r"Braintree\.", re.IGNORECASE),
        re.compile(r"js\.braintreegateway\.com", re.IGNORECASE),
        re.compile(r"client_token", re.IGNORECASE),
        re.compile(r"braintree\.js", re.IGNORECASE),
        re.compile(r"braintree-hosted-fields", re.IGNORECASE),
        re.compile(r"braintree-dropin", re.IGNORECASE),
        re.compile(r"braintree-v3", re.IGNORECASE),
        re.compile(r"braintree-client", re.IGNORECASE),
        re.compile(r"braintree-data-collector", re.IGNORECASE),
        re.compile(r"braintree-payment-form", re.IGNORECASE),
        re.compile(r"braintree-3ds-verify", re.IGNORECASE),
        re.compile(r"client\.create", re.IGNORECASE),
        re.compile(r"braintree\.min\.js", re.IGNORECASE),
        re.compile(r"data-braintree", re.IGNORECASE),
        re.compile(r"braintree\.tokenize", re.IGNORECASE),
        re.compile(r"braintree-dropin-ui", re.IGNORECASE),
    ],
    "Adyen": [
        re.compile(r"checkoutshopper-live\.adyen\.com", re.IGNORECASE),
        re.compile(r"adyen\.js", re.IGNORECASE),
        re.compile(r"data-adyen", re.IGNORECASE),
        re.compile(r"adyen-checkout", re.IGNORECASE),
        re.compile(r"adyen-payment", re.IGNORECASE),
        re.compile(r"adyen-components", re.IGNORECASE),
        re.compile(r"adyen-encrypted-data", re.IGNORECASE),
        re.compile(r"adyen-cse", re.IGNORECASE),
        re.compile(r"adyen-dropin", re.IGNORECASE),
        re.compile(r"adyen-web-checkout", re.IGNORECASE),
        re.compile(r"adyen\.encrypt", re.IGNORECASE),
        re.compile(r"checkoutshopper-test\.adyen\.com", re.IGNORECASE),
        re.compile(r"adyen-checkout__component", re.IGNORECASE),
        re.compile(r"adyen-payment-method", re.IGNORECASE),
        re.compile(r"adyen-action", re.IGNORECASE),
        re.compile(r"adyen\.min\.js", re.IGNORECASE),
    ],
    "Authorize.Net": [
        re.compile(r"js\.authorize\.net", re.IGNORECASE),
        re.compile(r"data-authorize", re.IGNORECASE),
        re.compile(r"authorize-payment", re.IGNORECASE),
        re.compile(r"anet\.js", re.IGNORECASE),
        re.compile(r"accept\.authorize\.net", re.IGNORECASE),
        re.compile(r"authorize-hosted-form", re.IGNORECASE),
        re.compile(r"merchantAuthentication", re.IGNORECASE),
        re.compile(r"data-api-login-id", re.IGNORECASE),
        re.compile(r"data-client-key", re.IGNORECASE),
        re.compile(r"Accept\.dispatchData", re.IGNORECASE),
    ],
    "Square": [
        re.compile(r"squareup\.com", re.IGNORECASE),
        re.compile(r"js\.squarecdn\.com", re.IGNORECASE),
        re.compile(r"square\.js", re.IGNORECASE),
        re.compile(r"data-square", re.IGNORECASE),
        re.compile(r"square-payment-form", re.IGNORECASE),
        re.compile(r"square-checkout-sdk", re.IGNORECASE),
        re.compile(r"square\.min\.js", re.IGNORECASE),
        re.compile(r"square-payment-flow", re.IGNORECASE),
        re.compile(r"square\.card", re.IGNORECASE),
        re.compile(r"data-square-application-id", re.IGNORECASE),
        re.compile(r"square\.createPayment", re.IGNORECASE),
    ],
    "Klarna": [
        re.compile(r"klarna\.com", re.IGNORECASE),
        re.compile(r"js\.klarna\.com", re.IGNORECASE),
        re.compile(r"klarna\.js", re.IGNORECASE),
        re.compile(r"data-klarna", re.IGNORECASE),
        re.compile(r"klarna-checkout", re.IGNORECASE),
        re.compile(r"klarna-onsite-messaging", re.IGNORECASE),
        re.compile(r"klarna-payments", re.IGNORECASE),
        re.compile(r"klarna\.min\.js", re.IGNORECASE),
        re.compile(r"klarna-order-id", re.IGNORECASE),
        re.compile(r"klarna-checkout-container", re.IGNORECASE),
        re.compile(r"klarna-load", re.IGNORECASE),
    ],
    "Checkout.com": [
        re.compile(r"js\.checkout\.com", re.IGNORECASE),
        re.compile(r"data-checkout", re.IGNORECASE),
        re.compile(r"checkout-sdk", re.IGNORECASE),
        re.compile(r"checkout-payment", re.IGNORECASE),
        re.compile(r"cko\.js", re.IGNORECASE),
        re.compile(r"checkout\.frames\.js", re.IGNORECASE),
        re.compile(r"cko-payment-token", re.IGNORECASE),
        re.compile(r"checkout\.init", re.IGNORECASE),
        re.compile(r"cko-hosted", re.IGNORECASE),
        re.compile(r"cko-card-token", re.IGNORECASE),
    ],
    "Paytm": [
        re.compile(r"paytm\.js", re.IGNORECASE),
        re.compile(r"data-paytm", re.IGNORECASE),
        re.compile(r"paytm-checkout", re.IGNORECASE),
        re.compile(r"paytm-payment-sdk", re.IGNORECASE),
        re.compile(r"paytm-wallet", re.IGNORECASE),
        re.compile(r"paytm\.allinonesdk", re.IGNORECASE),
        re.compile(r"paytm\.min\.js", re.IGNORECASE),
        re.compile(r"paytm-transaction-id", re.IGNORECASE),
        re.compile(r"paytm\.invoke", re.IGNORECASE),
        re.compile(r"paytm-checkout-js", re.IGNORECASE),
        re.compile(r"data-paytm-order-id", re.IGNORECASE),
    ],
    "Shopify Payments": [
        re.compile(r"data-shopify-payments", re.IGNORECASE),
        re.compile(r"shopify-checkout-sdk", re.IGNORECASE),
        re.compile(r"shopify-payment-api", re.IGNORECASE),
        re.compile(r"shopify-sdk", re.IGNORECASE),
        re.compile(r"shopify-express-checkout", re.IGNORECASE),
        re.compile(r"shopify_payments\.js", re.IGNORECASE),
        re.compile(r"shopify-payment-token", re.IGNORECASE),
        re.compile(r"shopify\.card", re.IGNORECASE),
        re.compile(r"shopify-checkout-api", re.IGNORECASE),
        re.compile(r"data-shopify-checkout", re.IGNORECASE),
    ],
    "Worldpay": [
        re.compile(r"worldpay\.js", re.IGNORECASE),
        re.compile(r"data-worldpay", re.IGNORECASE),
        re.compile(r"worldpay-checkout", re.IGNORECASE),
        re.compile(r"worldpay-payment-sdk", re.IGNORECASE),
        re.compile(r"worldpay-secure", re.IGNORECASE),
        re.compile(r"worldpay\.min\.js", re.IGNORECASE),
        re.compile(r"worldpay\.token", re.IGNORECASE),
        re.compile(r"worldpay-payment-form", re.IGNORECASE),
        re.compile(r"worldpay-3ds", re.IGNORECASE),
        re.compile(r"data-worldpay-token", re.IGNORECASE),
    ],
    "2Checkout": [
        re.compile(r"2co\.js", re.IGNORECASE),
        re.compile(r"data-2checkout", re.IGNORECASE),
        re.compile(r"2checkout-payment", re.IGNORECASE),
        re.compile(r"2co-checkout", re.IGNORECASE),
        re.compile(r"data-2co-seller-id", re.IGNORECASE),
        re.compile(r"2checkout\.convertplus", re.IGNORECASE),
        re.compile(r"2checkout\.token", re.IGNORECASE),
    ],
    "Amazon Pay": [
        re.compile(r"amazonpay\.js", re.IGNORECASE),
        re.compile(r"data-amazon-pay", re.IGNORECASE),
        re.compile(r"amazon-pay-button", re.IGNORECASE),
        re.compile(r"amazon-pay-checkout-sdk", re.IGNORECASE),
        re.compile(r"amazon-pay-wallet", re.IGNORECASE),
        re.compile(r"amazon-checkout\.js", re.IGNORECASE),
        re.compile(r"amazon-pay-token", re.IGNORECASE),
        re.compile(r"amazon-pay-sdk", re.IGNORECASE),
        re.compile(r"data-amazon-pay-merchant-id", re.IGNORECASE),
        re.compile(r"amazon-pay-signin", re.IGNORECASE),
        re.compile(r"amazon-pay-checkout-session", re.IGNORECASE),
    ],
    "Apple Pay": [
        re.compile(r"apple-pay\.js", re.IGNORECASE),
        re.compile(r"data-apple-pay", re.IGNORECASE),
        re.compile(r"apple-pay-button", re.IGNORECASE),
        re.compile(r"apple-pay-checkout-sdk", re.IGNORECASE),
        re.compile(r"apple-pay-session", re.IGNORECASE),
        re.compile(r"apple-pay-payment-request", re.IGNORECASE),
        re.compile(r"ApplePaySession", re.IGNORECASE),
        re.compile(r"apple-pay-merchant-id", re.IGNORECASE),
        re.compile(r"apple-pay-payment", re.IGNORECASE),
        re.compile(r"apple-pay-sdk", re.IGNORECASE),
        re.compile(r"data-apple-pay-token", re.IGNORECASE),
        re.compile(r"apple-pay-checkout", re.IGNORECASE),
        re.compile(r"apple-pay-domain", re.IGNORECASE),
    ],
    "Google Pay": [
        re.compile(r"googlepay\.js", re.IGNORECASE),
        re.compile(r"data-google-pay", re.IGNORECASE),
        re.compile(r"google-pay-button", re.IGNORECASE),
        re.compile(r"google-pay-checkout-sdk", re.IGNORECASE),
        re.compile(r"google-pay-tokenization", re.IGNORECASE),
        re.compile(r"google-pay-token", re.IGNORECASE),
        re.compile(r"google-pay-payment-method", re.IGNORECASE),
        re.compile(r"data-google-pay-merchant-id", re.IGNORECASE),
        re.compile(r"google-pay-checkout", re.IGNORECASE),
        re.compile(r"google-pay-sdk", re.IGNORECASE),
    ],
    "Mollie": [
        re.compile(r"mollie\.js", re.IGNORECASE),
        re.compile(r"data-mollie", re.IGNORECASE),
        re.compile(r"mollie-checkout", re.IGNORECASE),
        re.compile(r"mollie-payment-sdk", re.IGNORECASE),
        re.compile(r"mollie-components", re.IGNORECASE),
        re.compile(r"mollie\.min\.js", re.IGNORECASE),
        re.compile(r"mollie-payment-token", re.IGNORECASE),
        re.compile(r"mollie-create-payment", re.IGNORECASE),
        re.compile(r"data-mollie-profile-id", re.IGNORECASE),
        re.compile(r"mollie-checkout-form", re.IGNORECASE),
        re.compile(r"mollie-redirect", re.IGNORECASE),
    ],
    "Opayo": [
        re.compile(r"opayo\.js", re.IGNORECASE),
        re.compile(r"data-opayo", re.IGNORECASE),
        re.compile(r"opoayo-checkout", re.IGNORECASE),
        re.compile(r"opayo-payment-sdk", re.IGNORECASE),
        re.compile(r"opayo-form", re.IGNORECASE),
        re.compile(r"opayo\.min\.js", re.IGNORECASE),
        re.compile(r"opayo-payment-token", re.IGNORECASE),
        re.compile(r"opayo-3ds", re.IGNORECASE),
        re.compile(r"data-opayo-merchant-id", re.IGNORECASE),
        re.compile(r"opayo-hosted", re.IGNORECASE),
    ],
    "Paddle": [
        re.compile(r"paddle_button\.js", re.IGNORECASE),
        re.compile(r"paddle\.js", re.IGNORECASE),
        re.compile(r"data-paddle", re.IGNORECASE),
        re.compile(r"paddle-checkout-sdk", re.IGNORECASE),
        re.compile(r"paddle-product-id", re.IGNORECASE),
        re.compile(r"paddle\.min\.js", re.IGNORECASE),
        re.compile(r"paddle-checkout", re.IGNORECASE),
        re.compile(r"data-paddle-vendor-id", re.IGNORECASE),
        re.compile(r"paddle\.Checkout\.open", re.IGNORECASE),
        re.compile(r"paddle-transaction-id", re.IGNORECASE),
        re.compile(r"paddle-hosted", re.IGNORECASE),
    ],
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
        re.compile(r"data-sitekey", re.IGNORECASE),
        re.compile(r"nocaptcha", re.IGNORECASE),
        re.compile(r"recaptcha\.net", re.IGNORECASE),
        re.compile(r"www\.google\.com/recaptcha", re.IGNORECASE),
        re.compile(r"grecaptcha\.execute", re.IGNORECASE),
        re.compile(r"grecaptcha\.render", re.IGNORECASE),
        re.compile(r"grecaptcha\.ready", re.IGNORECASE),
        re.compile(r"recaptcha-token", re.IGNORECASE),
    ],
    "hCaptcha": [
        re.compile(r"hcaptcha", re.IGNORECASE),
        re.compile(r"assets\.hcaptcha\.com", re.IGNORECASE),
        re.compile(r"hcaptcha\.com/1/api\.js", re.IGNORECASE),
        re.compile(r"data-hcaptcha-sitekey", re.IGNORECASE),
        re.compile(r"hcaptcha-invisible", re.IGNORECASE),
        re.compile(r"hcaptcha\.execute", re.IGNORECASE),
    ],
    "Turnstile": [
        re.compile(r"turnstile", re.IGNORECASE),
        re.compile(r"challenges\.cloudflare\.com", re.IGNORECASE),
        re.compile(r"cf-turnstile-response", re.IGNORECASE),
        re.compile(r"data-sitekey", re.IGNORECASE),
        re.compile(r"__cf_chl_", re.IGNORECASE),
        re.compile(r"cf_clearance", re.IGNORECASE),
    ],
    "Arkose Labs": [
        re.compile(r"arkose-labs", re.IGNORECASE),
        re.compile(r"funcaptcha", re.IGNORECASE),
        re.compile(r"client-api\.arkoselabs\.com", re.IGNORECASE),
        re.compile(r"fc-token", re.IGNORECASE),
        re.compile(r"fc-widget", re.IGNORECASE),
        re.compile(r"arkose", re.IGNORECASE),
        re.compile(r"press and hold", re.IGNORECASE),
        re.compile(r"funcaptcha\.com", re.IGNORECASE),
    ],
    "GeeTest": [
        re.compile(r"geetest", re.IGNORECASE),
        re.compile(r"gt_captcha_obj", re.IGNORECASE),
        re.compile(r"gt\.js", re.IGNORECASE),
        re.compile(r"geetest_challenge", re.IGNORECASE),
        re.compile(r"geetest_validate", re.IGNORECASE),
        re.compile(r"geetest_seccode", re.IGNORECASE),
    ],
    "BotDetect": [
        re.compile(r"botdetectcaptcha", re.IGNORECASE),
        re.compile(r"BotDetect", re.IGNORECASE),
        re.compile(r"BDC_CaptchaImage", re.IGNORECASE),
        re.compile(r"CaptchaCodeTextBox", re.IGNORECASE),
    ],
    "KeyCAPTCHA": [
        re.compile(r"keycaptcha", re.IGNORECASE),
        re.compile(r"kc_submit", re.IGNORECASE),
        re.compile(r"kc__widget", re.IGNORECASE),
        re.compile(r"s_kc_cid", re.IGNORECASE),
    ],
    "Anti Bot Detection": [
        re.compile(r"fingerprintjs", re.IGNORECASE),
        re.compile(r"js\.challenge", re.IGNORECASE),
        re.compile(r"checking your browser", re.IGNORECASE),
        re.compile(r"verify you are human", re.IGNORECASE),
        re.compile(r"please enable javascript and cookies", re.IGNORECASE),
        re.compile(r"sec-ch-ua-platform", re.IGNORECASE),
    ],
    "Captcha": [
        re.compile(r"captcha-container", re.IGNORECASE),
        re.compile(r"captcha-box", re.IGNORECASE),
        re.compile(r"captcha-frame", re.IGNORECASE),
        re.compile(r"captcha_input", re.IGNORECASE),
        re.compile(r"id=\"captcha\"", re.IGNORECASE),
        re.compile(r"class=\"captcha\"", re.IGNORECASE),
        re.compile(r"iframe.+?captcha", re.IGNORECASE),
        re.compile(r"data-captcha-sitekey", re.IGNORECASE),
    ],
}

# Checkout URL patterns
CHECKOUT_PATTERNS = [
    re.compile(r"/(cart|checkout|buy|purchase|subscribe|payment|order)", re.IGNORECASE),
    re.compile(r"shopify\.com/checkout", re.IGNORECASE),
    re.compile(r"woocommerce-checkout", re.IGNORECASE),
]

async def detect_technologies(page: Page, html: str) -> List[str]:
    """Detect technologies in HTML and JavaScript globals."""
    detected_tech = []
    
    # Scan HTML for patterns
    for tech, patterns in TECH_PATTERNS.items():
        if any(p.search(html) for p in patterns):
            detected_tech.append(tech)
    
    # Check JavaScript globals
    try:
        js_globals = await page.evaluate("""
            () => {
                return {
                    hasStripe: typeof Stripe !== 'undefined',
                    hasPayPal: typeof paypal !== 'undefined',
                    hasRazorpay: typeof Razorpay !== 'undefined',hasBraintree: typeof braintree !== 'undefined',
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
                    hasShopify: typeof Shopify !== 'undefined'
                };
            }
        """)
        for key, value in js_globals.items():
            if value:
                tech_name = key.replace("has", "")
                if tech_name not in detected_tech:
                    detected_tech.append(tech_name)
    except Exception as e:
        logger.error(f"Error evaluating JS globals: {str(e)}")
    
    return detected_tech

async def find_checkout_urls(page: Page, base_url: str, html: str) -> tuple[List[str], List[Dict[str, str]]]:
    """Find potential checkout URLs via link analysis and network inspection."""
    checkout_urls = set()
    network_requests = []
    
    # Parse HTML for links
    soup = BeautifulSoup(html, "html.parser")
    for link in soup.find_all(["a", "button", "input"]):
        href = link.get("href") or link.get("action")
        text = link.get_text().lower()
        if href and (any(p.search(href) for p in CHECKOUT_PATTERNS) or 
                     any(keyword in text for keyword in ["checkout", "buy", "cart", "subscribe", "pricing"])):
            full_url = urljoin(base_url, href)
            checkout_urls.add(full_url)
    
    # Network inspection
    def capture_request(request):
        network_requests.append({"url": request.url, "method": request.method})
    
    page.on("request", capture_request)
    
    # Simulate clicks on potential checkout links
    try:
        links = await page.locator("a, button, input[type='submit']").all()
        for link in links:
            text = (await link.inner_text()).lower()
            if text and re.search(r"pricing|buy|subscribe|checkout|cart", text, re.IGNORECASE):
                try:
                    await link.click(timeout=5000)
                    await page.wait_for_timeout(random.randint(300, 1000))
                except Exception as e:
                    logger.error(f"Error clicking link {text}: {str(e)}")
    except Exception as e:
        logger.error(f"Error during link interaction: {str(e)}")
    
    # Analyze network requests
    for req in network_requests:
        if any(p.search(req["url"]) for p in CHECKOUT_PATTERNS):
            checkout_urls.add(req["url"])
    
    return list(checkout_urls), network_requests

async def scan_url(url: str, max_retries: int = 3) -> Dict:
    """Scan a single URL with retries for technologies and checkout URLs."""
    errors = []
    technologies = []
    checkout_urls = []
    network_insights = []
    
    async with async_playwright() as p:
        for attempt in range(max_retries):
            try:
                logger.info(f"Attempt {attempt + 1}: Connecting to Bright Data Browser API")
                # Explicit proxy configuration
                browser = await p.chromium.connect_over_cdp(
                    "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222",
                    timeout=30000
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
                    proxy={
                        "server": "http://brd.superproxy.io:22225",
                        "username": "brd-customer-hl_55395c6c-zone-residential_proxy1",
                        "password": "yv8ient65hzb"
                    }
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
                    response = await page.goto(url, timeout=45000, wait_until="domcontentloaded")
                    if not response or response.status >= 400:
                        errors.append(f"Failed to load URL: {response.status if response else 'No response'}")
                        continue
                except Exception as e:
                    errors.append(f"Navigation error: {str(e)}")
                    continue
                
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
                return {
                    "url": url,
                    "technologies": technologies,
                    "checkout_urls": checkout_urls,
                    "network_insights": network_insights,
                    "errors": errors if errors else None
                }
            
            except Error as e:
                errors.append(f"Browser connection error (attempt {attempt + 1}): {str(e)}")
                logger.error(f"Attempt {attempt + 1} failed: {str(e)}")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
                continue
            finally:
                if 'context' in locals():
                    await context.close()
                if 'browser' in locals():
                    await browser.close()
    
    return {
        "url": url,
        "technologies": [],
        "checkout_urls": [],
        "network_insights": [],
        "errors": errors or ["All connection attempts to Bright Data failed"]
    }

@app.get("/gatecheck/", response_model=DetectionResponse)
async def gatecheck(url: str):
    """API endpoint to detect payment gateways, e-commerce platforms, and checkout URLs."""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed_url = urlparse(url)
    if not parsed_url.scheme or not parsed_url.netloc:
        raise HTTPException(status_code=400, detail="Invalid URL provided")
    
    result = await scan_url(url)
    return DetectionResponse(**result)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
