import asyncio
import re
import os
import random
from typing import List, Dict, Optional
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import logging
import requests
import xml.etree.ElementTree as ET
from fake_useragent import UserAgent

# Configure logging with detailed format
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize fake user agent for randomization
ua = UserAgent()

# Define technology fingerprints (partial, as requested)
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

async def find_checkout_urls(base_url: str) -> List[str]:
    """Parse sitemap.xml, sitemap_index.xml, or robots.txt to extract potential checkout/product URLs."""
    logger.info(f"Fetching sitemap for {base_url}")
    sitemap_urls = [f"{base_url}/sitemap.xml", f"{base_url}/sitemap_index.xml"]
    checkout_urls = []
    for sitemap_url in sitemap_urls:
        try:
            response = requests.get(sitemap_url, timeout=10)
            response.raise_for_status()
            root = ET.fromstring(response.content)
            checkout_urls.extend([
                loc.text for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc")
                if re.search(r"/(order|checkout|pricing|buy|subscribe|cart|payment)/", loc.text, re.IGNORECASE)
            ])
            logger.info(f"Found {len(checkout_urls)} potential checkout URLs in {sitemap_url}: {checkout_urls}")
            if checkout_urls:
                break
        except Exception as e:
            logger.error(f"Error fetching sitemap {sitemap_url}: {str(e)}")
    
    if not checkout_urls:
        try:
            response = requests.get(f"{base_url}/robots.txt", timeout=10)
            response.raise_for_status()
            checkout_urls = [
                line.split(" ")[-1] for line in response.text.splitlines()
                if "Disallow" in line and re.search(r"/(order|checkout|pricing|buy|subscribe|cart|payment)/", line, re.IGNORECASE)
            ]
            checkout_urls = [u if u.startswith(("http://", "https://")) else f"{base_url.rstrip('/')}/{u.lstrip('/')}" for u in checkout_urls]
            logger.info(f"Found {len(checkout_urls)} potential checkout URLs in robots.txt: {checkout_urls}")
        except Exception as e:
            logger.error(f"Error fetching robots.txt for {base_url}: {str(e)}")
    
    return checkout_urls

async def detect_technologies(url: str, max_retries: int = 2) -> Dict[str, List[str]]:
    """Detect payment gateways and e-commerce platforms with retries and human-like behavior."""
    logger.info(f"Starting technology detection for URL: {url}")
    technologies = []
    for attempt in range(max_retries):
        try:
            async with async_playwright() as p:
                logger.info(f"Attempt {attempt + 1}: Connecting to Bright Data Browser API")
                browser = await p.chromium.connect_over_cdp(
                    "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222"
                )
                context = await browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=ua.random,
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

                # Human-like navigation
                logger.info(f"Navigating to {url}")
                response = await page.goto(url, timeout=45000, wait_until="networkidle")
                if not response or response.status >= 400:
                    raise Exception(f"Failed to load URL: {response.status if response else 'No response'}")
                logger.info(f"Page loaded successfully with status: {response.status}")

                # Simulate human behavior
                logger.info("Simulating human-like interactions")
                await page.mouse.move(random.randint(100, 800), random.randint(100, 600))
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(random.randint(500, 1500))  # Random delay

                # Click potential checkout links to trigger dynamic content
                logger.info("Attempting to click checkout-related links")
                links = await page.locator("a, button, input[type='submit']").all()
                for link in links:
                    text = await link.inner_text()
                    if text and re.search(r"pricing|buy|subscribe|checkout", text.lower(), re.IGNORECASE):
                        try:
                            await link.click(timeout=5000)
                            await page.wait_for_timeout(random.randint(300, 1000))
                            break
                        except Exception as e:
                            logger.error(f"Error clicking link {text}: {str(e)}")

                # Check for checkout links/buttons
                logger.info("Extracting potential checkout links/buttons")
                checkout_links = [
                    await link.get_attribute("href") or await link.evaluate("el => el.form?.action")
                    for link in links
                    if await link.inner_text() and re.search(
                        r"buy|pricing|subscribe|checkout|cart|order|payment",
                        (await link.inner_text()).lower(),
                        re.IGNORECASE
                    )
                ]
                checkout_links = [link for link in checkout_links if link]
                logger.info(f"Found {len(checkout_links)} potential checkout links: {checkout_links}")

                # Get page content
                logger.info("Extracting page content")
                html = await page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Extract script sources
                logger.info("Extracting script sources")
                script_urls = [
                    script.get("src", "") for script in soup.find_all("script") if script.get("src")
                ]
                logger.info(f"Found {len(script_urls)} script URLs: {script_urls}")

                # Extract inline scripts
                logger.info("Extracting inline scripts")
                inline_scripts = [
                    script.string for script in soup.find_all("script") if script.string
                ]
                logger.info(f"Found {len(inline_scripts)} inline scripts")

                # Extract data attributes
                logger.info("Extracting data attributes")
                data_attrs = [
                    attr for elem in soup.find_all(True) for attr in elem.attrs if attr.startswith("data-")
                ]
                logger.info(f"Found {len(data_attrs)} data attributes: {data_attrs}")

                # Evaluate JavaScript globals
                logger.info("Evaluating JavaScript globals")
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
                logger.info(f"JavaScript globals evaluation result: {js_globals}")

                # Combine content for pattern matching
                logger.info("Combining content for pattern matching")
                all_content = (
                    html + " ".join(script_urls) + " ".join(inline_scripts) + " ".join(data_attrs)
                )
                logger.info(f"Total content length: {len(all_content)} characters")

                # Scan for technologies
                logger.info("Scanning for technologies")
                matched_patterns = []
                for tech, patterns in TECH_PATTERNS.items():
                    for pattern in patterns:
                        if pattern.search(all_content):
                            technologies.append(tech)
                            matched_patterns.append(f"{tech}: {pattern.pattern}")
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
                    logger.info(f"Matched patterns for {tech}: {matched_patterns}")
                    logger.info(f"Detected technologies for {tech}: {technologies}")

                technologies = list(set(technologies))
                logger.info(f"Final unique technologies: {technologies}")

                await browser.close()
                logger.info(f"Browser closed for {url}")
                return {"url": url, "technologies": technologies, "error": None}

        except Exception as e:
            logger.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
            if attempt == max_retries - 1:
                return {"url": url, "technologies": [], "error": str(e)}
            await asyncio.sleep(2)  # Wait before retry

async def detect_technologies_with_checkout(url: str) -> DetectionResponse:
    """Detect technologies on the main URL and potential checkout pages concurrently."""
    logger.info(f"Processing URL with checkout detection: {url}")

    # Get potential checkout URLs from sitemap
    checkout_urls = await find_checkout_urls(url)
    checkout_urls = [u for u in checkout_urls if u.startswith(("http://", "https://"))]
    if not checkout_urls:
        logger.info("No checkout URLs found in sitemap, trying link analysis")

        # Fallback to link analysis on homepage
        async with async_playwright() as p:
            logger.info("Connecting to Bright Data Browser API for link analysis")
            browser = await p.chromium.connect_over_cdp(
                "wss://brd-customer-hl_55395c6c-zone-residential_proxy1:yv8ient65hzb@brd.superproxy.io:9222"
            )
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=ua.random,
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

            try:
                await page.goto(url, timeout=45000, wait_until="networkidle")
                links = await page.locator("a, button, input[type='submit']").all()
                checkout_urls = [
                    await link.get_attribute("href") or await link.evaluate("el => el.form?.action")
                    for link in links
                    if await link.inner_text() and re.search(
                        r"buy|pricing|subscribe|checkout|cart|order|payment",
                        (await link.inner_text()).lower(),
                        re.IGNORECASE
                    )
                ]
                checkout_urls = [u for u in checkout_urls if u and u.startswith(("http://", "https://"))]
                logger.info(f"Found {len(checkout_urls)} checkout URLs via link analysis: {checkout_urls}")
                await browser.close()
            except Exception as e:
                logger.error(f"Error in link analysis for {url}: {str(e)}")
                await browser.close()

    # Add original URL to check
    all_urls = [url] + checkout_urls[:2]  # Limit to 2 checkout URLs for speed
    logger.info(f"Checking technologies on {len(all_urls)} URLs: {all_urls}")

    # Run detection concurrently
    results = await asyncio.gather(
        *[detect_technologies(u) for u in all_urls],
        return_exceptions=True
    )

    # Aggregate results
    for result in results:
        if isinstance(result, dict) and result["technologies"]:
            logger.info(f"Technologies found on {result['url']}: {result['technologies']}")
            return DetectionResponse(**result)
    
    # Return result from original URL if no technologies found
    logger.info("No technologies found on any URLs, returning original URL result")
    return DetectionResponse(**results[0]) if isinstance(results[0], dict) else DetectionResponse(url=url, technologies=[], error="No technologies detected")
    
@app.get("/gatecheck/", response_model=DetectionResponse)
async def gatecheck(url: str):
    """
    API endpoint to detect payment gateways and e-commerce platforms.
    Example: /gatecheck/?url=https://example.com
    """
    logger.info(f"Received gatecheck request for URL: {url}")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
        logger.info(f"Added https:// to URL: {url}")
    parsed_url = urlparse(url)
    logger.info(f"Parsed URL: scheme={parsed_url.scheme}, netloc={parsed_url.netloc}")
    if not parsed_url.scheme or not parsed_url.netloc:
        logger.warning(f"Invalid URL provided: {url}")
        raise HTTPException(status_code=400, detail="Invalid URL provided")

    result = await detect_technologies_with_checkout(url)
    logger.info(f"Gatecheck result for {url}: {result}")
    return result

@app.get("/")
async def root():
    logger.info("Received request to root endpoint")
    return {"message": "Welcome to the Payment Gateway & E-Commerce Detector API. Use /gatecheck/?url=<your_url> to detect technologies."}

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
    logger.info("Starting Uvicorn server locally")
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
