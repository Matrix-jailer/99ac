import os
import asyncio
import re
from fastapi.responses import FileResponse, Response  # Add Response here
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import logging

# Configure logging with more detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Define technology fingerprints (payment gateways + e-commerce platforms)

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

app = FastAPI(title="Payment Gateway & E-Commerce Detector API")

# Request model
class URLRequest(BaseModel):
    url: str

# Response model
class DetectionResponse(BaseModel):
    url: str
    technologies: List[str]
    error: Optional[str] = None

async def detect_technologies(url: str) -> Dict[str, List[str]]:
    """
    Detect payment gateways, e-commerce platforms, and protections using Playwright Stealth.
    """
    logger.info(f"Starting technology detection for URL: {url}")  # Logger 1
    technologies = []
    try:
        async with async_playwright() as p:
            logger.info("Launching Playwright Chromium browser")  # Logger 2
            # Launch browser with stealth settings
            browser = await p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-infobars",
                    "--window-size=1920,1080",
                ],
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            )
            await stealth_async(context)
            page = await context.new_page()

            # Navigate to URL
            logger.info(f"Navigating to {url}")  # Logger 3
            response = await page.goto(url, timeout=30000, wait_until="domcontentloaded")
            if not response or response.status >= 400:
                raise Exception(f"Failed to load URL: {response.status if response else 'No response'}")
            logger.info(f"Page loaded successfully with status: {response.status}")  # Logger 4

            # Get page content
            logger.info("Extracting page content")  # Logger 5
            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            # Extract script sources
            logger.info("Extracting script sources")  # Logger 6
            script_urls = [
                script.get("src", "") for script in soup.find_all("script") if script.get("src")
            ]
            logger.info(f"Found {len(script_urls)} script URLs: {script_urls}")  # Logger 7

            # Extract inline scripts
            logger.info("Extracting inline scripts")  # Logger 8
            inline_scripts = [
                script.string for script in soup.find_all("script") if script.string
            ]
            logger.info(f"Found {len(inline_scripts)} inline scripts")  # Logger 9

            # Extract data attributes
            logger.info("Extracting data attributes")  # Logger 10
            data_attrs = [
                attr for elem in soup.find_all(True) for attr in elem.attrs if attr.startswith("data-")
            ]
            logger.info(f"Found {len(data_attrs)} data attributes: {data_attrs}")  # Logger 11

            # Evaluate JavaScript globals in browser context
            logger.info("Evaluating JavaScript globals")  # Logger 12
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
                        hasGooglePay: typeof window.google === 'undefined' ? false : typeof google.payments?.api !== 'undefined',
                        hasMollie: typeof Mollie !== 'undefined',
                        hasOpayo: typeof Opayo !== 'undefined',
                        hasPaddle: typeof Paddle !== 'undefined',
                        hasShopify: typeof Shopify !== 'undefined',
                    };
                }
            """)
            logger.info(f"JavaScript globals evaluation result: {js_globals}")  # Logger 13

            # Combine all content to scan
            logger.info("Combining content for pattern matching")  # Logger 14
            all_content = (
                html + " ".join(script_urls) + " ".join(inline_scripts) + " ".join(data_attrs)
            )
            logger.info(f"Total content length: {len(all_content)} characters")  # Logger 15

            # Scan for technologies
            logger.info("Scanning for technologies")  # Logger 16
            matched_patterns = []
            for tech, patterns in TECH_PATTERNS.items():
                if any(pattern.search(all_content) for pattern in patterns):
                    technologies.append(tech)
                # Additional JS global checks
                if tech == "Stripe" and js_globals.get("hasStripe"):
                    technologies.append(tech)
                elif tech == "PayPal" and js_globals.get("hasPayPal"):
                    technologies.append(tech)
                elif tech == "Razorpay" and js_globals.get("hasRazorpay"):
                    technologies.append(tech)
                elif tech == "Braintree" and js_globals.get("hasBraintree"):
                    technologies.append(tech)
                elif tech == "Adyen" and js_globals.get("hasAdyen"):
                    technologies.append(tech)
                elif tech == "Authorize.Net" and js_globals.get("hasAuthorizeNet"):
                    technologies.append(tech)
                elif tech == "Square" and js_globals.get("hasSquare"):
                    technologies.append(tech)
                elif tech == "Klarna" and js_globals.get("hasKlarna"):
                    technologies.append(tech)
                elif tech == "Checkout.com" and js_globals.get("hasCheckoutCom"):
                    technologies.append(tech)
                elif tech == "Paytm" and js_globals.get("hasPaytm"):
                    technologies.append(tech)
                elif tech == "Shopify Payments" and js_globals.get("hasShopifyPayments"):
                    technologies.append(tech)
                elif tech == "Worldpay" and js_globals.get("hasWorldpay"):
                    technologies.append(tech)
                elif tech == "2Checkout" and js_globals.get("has2Checkout"):
                    technologies.append(tech)
                elif tech == "Amazon Pay" and js_globals.get("hasAmazonPay"):
                    technologies.append(tech)
                elif tech == "Apple Pay" and js_globals.get("hasApplePay"):
                    technologies.append(tech)
                elif tech == "Google Pay" and js_globals.get("hasGooglePay"):
                    technologies.append(tech)
                elif tech == "Mollie" and js_globals.get("hasMollie"):
                    technologies.append(tech)
                elif tech == "Opayo" and js_globals.get("hasOpayo"):
                    technologies.append(tech)
                elif tech == "Paddle" and js_globals.get("hasPaddle"):
                    technologies.append(tech)
                elif tech == "Shopify" and js_globals.get("hasShopify"):
                    technologies.append(tech)
                logger.info(f"Matched patterns: {matched_patterns}")  # Logger 17
                logger.info(f"Detected technologies: {technologies}")  # Logger 18

            # Remove duplicates
            technologies = list(set(technologies))
            logger.info(f"Final unique technologies: {technologies}")  # Logger 19

            await browser.close()
            logger.info(f"Browser closed for {url}")  # Logger 20
            return {"url": url, "technologies": technologies, "error": None}
            
    except Exception as e:
        logger.error(f"Error processing {url}: {str(e)}")  # Logger 21
        logger.error(f"Error processing {url}: {str(e)}")
        return {"url": url, "technologies": [], "error": str(e)}

@app.get("/gatecheck/", response_model=DetectionResponse)
async def gatecheck(url: str):
    """
    API endpoint to detect payment gateways and e-commerce platforms.
    Example: /gatecheck/?url=https://example.com
    """
    # Validate URL
    logger.info(f"Received gatecheck request for URL: {url}")  # Logger 22
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        logger.info(f"Added https:// to URL: {url}")  # Logger 23
    parsed_url = urlparse(url)
    logger.info(f"Parsed URL: scheme={parsed_url.scheme}, netloc={parsed_url.netloc}")  # Logger 24
    if not parsed_url.scheme or not parsed_url.netloc:
        logger.warning(f"Invalid URL provided: {url}")  # Logger 25
        raise HTTPException(status_code=400, detail="Invalid URL provided")

    # Run detection
    result = await detect_technologies(url)
    logger.info(f"Gatecheck result for {url}: {result}")  # Logger 26
    return DetectionResponse(**result)
@app.get("/")
async def root():
    logger.info("Received request to root endpoint")  # Logger 27
    return {"message": "Welcome to the Payment Gateway & E-Commerce Detector API. Use /gatecheck/?url=<your_url> to detect technologies."}

from fastapi.responses import FileResponse

@app.get("/favicon.ico")
async def favicon():
    logger.info("Received request for favicon.ico")
    favicon_path = "favicon.ico"
    if os.path.exists(favicon_path):
        logger.info(f"Serving favicon from {favicon_path}")
        return FileResponse(favicon_path)
    logger.info("No favicon found, returning 204 No Content")
    return Response(status_code=204)

if __name__ == "__main__":
    logger.info("Starting Uvicorn server locally")  # Logger 31
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
