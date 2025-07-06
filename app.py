from fastapi import FastAPI, HTTPException
import asyncio
import re
from playwright.async_api import async_playwright
from fastapi.responses import JSONResponse

app = FastAPI(title="Gateway Scanner API", description="API to scan websites for payment gateways, captchas, platforms, and 3D Secure")

# Placeholder for ALL_PATTERNS (you'll add this later)
ALL_PATTERNS = {
    "Stripe": [
        r"stripe.com", r"api.stripe.com", r"stripe_checkout", r"stripe_payment_intent", r"stripe-button", r"checkout.stripe.com", r"\.hb-cc-stripe",
        r"RedirectToStripeCheckout", r"STRIPE_ELEMENTS_OPTIONS", r"handleStripeAction", r"stripe_session_id",
        r"stripe-confirm", r"stripe_session_id", r"stripePubKey", r"pk_live_",
        r"stripePaymentMethodId", r"js.stripe.com", r"stripe.js", r"stripe.min.js",
        r"client_secret", r"payment_intent", r"data-stripe", r"strip-payment-element",
        r"stripe-elements", r"stripe-checkout", r"hooks.stripe.com", r"m.stripe.network",
        r"stripe__input", r"stripe-card-element", r"stripe-v3ds", r"confirmCardPayment",
        r"createPaymentMethod", r"stripePublicKey", r"stripe.handleCardAction",
        r"elements.create", r"js.stripe.com/v3/hcaptcha-invisible", r"js.stripe.com/v3",
        r"stripe.createToken", r"stripe-payment-request", r"stripe__frame",
        r"api.stripe.com/v1/payment_methods", r"api.stripe.com/v1/tokens",
        r"stripe.com/docs", r"checkout.stripe.com", r"stripe-js", r"stripe-redirect",
        r"stripe-payment", r"stripe.network", r"stripe-checkout.js", r"stripeCardElement", r"stripeInstance", r"stripePaymentMethod", r"stripePaymentRequest", r"stripeDigitalWalletCompleteCallback"
    ],
    "PayPal": [
        r"api.paypal.com", r"ShopifyPaypalV4VisibilityTracking", r"action\s*=\s*['\"]https://www\.paypal\.com/cgi-bin/webscr['\"]", r"paypal.com", r"paypal.js",
        r"paypalobjects.com", r"paypal_express_checkout", r"PAYPAL_EXPRESS_CHECKOUT", r"\.hb-cc-paypal",
        r"paypal-button", r"paypal-checkout-sdk", r"paypal.com.*sdk.js", r"paypal-smart-button",
        r"paypal.*transaction-id", r"paypal-rest-sdk", r".payment_method_paypal",
        r"api-transaction/paypal", r"PayPal.Buttons", r"paypal.Buttons",
        r"data-paypal-client-id", r"paypal.com/sdk/js", r"paypal.Order.create",
        r"paypal-checkout-component", r"api-m.paypal.com", r"paypal-funding",
        r"paypal-hosted-fields", r"paypal-transaction-id", r"paypal.me",
        r"paypal.com/v2/checkout", r"paypal-checkout",
        r"sdk.paypal.com", r"gotopaypalexpresscheckout", r"e.PaymentMethodTypes.PAYPAL_GATEWAY", r"PayPalPlaceOrderButton", r"paypalInitialized", r"payPalGateway", r"hasPayPalGateway", r"payPalOrderId", r"paypal-init-error"
    ],
    "Braintree": [
        r"api.braintreegateway.com", r"api.braintreegateway.com", r"js.braintreegateway.com",
        r"braintree\.client\.create", r"js.braintreegateway.com.*braintree.js", r"braintree-hosted-fields", r"braintree-dropin",
        r"braintree-v3", r"braintree-client", r"braintree-data-collector",
        r"braintree-payment-form", r"braintree-3ds-verify", r"braintree.*client_token",
        r"braintree.min.js", r"assets.braintreegateway.com", r"braintree.setup",
        r"data-braintree", r"braintree.tokenize", r"braintree-dropin-ui", r"braintree.com"
    ],
    "Adyen": [
        r"checkoutshopper-live.adyen.com", r"adyen.com/hpp", r"adyen.js", r"data-adyen",
        r"adyen.com", r"adyen-checkout", r"adyen-payment", r"adyen-components",
        r"adyen-encrypted-data", r"adyen-cse", r"adyen-dropin", r"adyen-web-checkout",
        r"live.adyen-services.com", r"adyen.encrypt", r"checkoutshopper-test.adyen.com",
        r"adyen-checkout__component", r"adyen.com/v1", r"adyen-payment-method",
        r"adyen-action", r"adyen.min.js"
    ],
    "Authorize.Net": [
        r"authorize.net", r"js.authorize.net", r"anet.js", r"data-authorize",
        r"authorize-payment", r"apitest.authorize.net", r"accept.authorize.net",
        r"api.authorize.net", r"authorize-hosted-form", r"merchantAuthentication",
        r"data-api-login-id", r"data-client-key", r"Accept.dispatchData",
        r"api.authorize.net/xml/v1", r"accept.authorize.net/payment",
        r"authorize.net/profile"
    ],
    "Square": [
        r"squareup.com", r"square_customer_account_id", r"js.squarecdn.com", r"SqPaymentForm", r"square-cc-payment-option-card-input", r"data-square", r"SquareCreditCardPaymentOption", r"square-credit-card__loader", r"checkout.square_pay.missing_card", r"showSquarePayOptInCheckbox", r"checkout.payment.options.squareCC", r"square-cc-payment-option-country-select", r"square_buyer_id", r"square_pay_buyer_type", r"square_pay_buyer_type", r"sqpaymentform", r"(?i)cdn\.squareup\.com",
        r"square-payment-form", r"square-checkout-sdk", r"connect.squareup.com",
        r"square.min.js", r"squarecdn.com", r"squareupsandbox.com", r"square-pay__icon",
        r"sandbox.web.squarecdn.com", r"square-payment-flow", r"square.card",
        r"squareup.com/payments", r"data-square-application-id", r"square.createPayment", r"SQUARE_3DS_IFRAME_TIMEOUT", r"e.squareGateway", r"square-location-id", r"e.square-location-id", r"square-pay-opt-in-checkbox", r"square-credit-card-payment-option-checkbox-container"
    ],
    "Klarna": [
        r"klarna.com", r"js.klarna.com", r"klarna.js", r"data-klarna",
        r"klarna-checkout", r"klarna-onsite-messaging", r"playground.klarna.com",
        r"klarna-payments", r"klarna.min.js", r"klarna-order-id",
        r"klarna-checkout-container", r"klarna-load", r"api.klarna.com"
    ],
    "Checkout.com": [
        r"api.checkout.com", r"data-cko", r"cko-session", r"cko-sdk",
        r"js.checkout.com/cko.js", r"js.checkout.com", r"secure.checkout.com",
        r"checkout.frames.js", r"api.sandbox.checkout.com", r"cko-payment-token",
        r"cko.init", r"cko-hosted", r"checkout.com/v2", r"cko-card-token"
    ],
    "Razorpay": [
        r"checkout.razorpay.com", r"razorpay.js", r"data-razorpay", r"razorpay-checkout",
        r"razorpay-payment-api", r"razorpay-sdk", r"razorpay-payment-button",
        r"razorpay-order-id", r"api.razorpay.com", r"razorpay.min.js",
        r"payment_box payment_method_razorpay", r"cdn.razorpay.com",
        r"rzp_payment_icon.svg", r"razorpay.checkout", r"data-razorpay-key",
        r"razorpay_payment_id", r"checkout.razorpay.com/v1", r"razorpay-hosted"
    ],
    "Paytm": [
        r"securegw.paytm.in", r"api.paytm.com", r"paytm.js", r"data-paytm",
        r"paytm-checkout", r"paytm-payment-sdk", r"paytm-wallet", r"paytm.allinonesdk",
        r"securegw-stage.paytm.in", r"paytm.min.js", r"paytm-transaction-id",
        r"paytm.invoke", r"paytm-checkout-js", r"data-paytm-order-id"
    ],
    "Shopify Payments": [
        r"pay.shopify.com", r"data-shopify-payments", r"shopify-payments-sdk",
        r"api.shopify.com/payments", r"shopify-payments-sdk", r"shopify-express-checkout",
        r"shopify_payments.js", r"api.shopify.com/checkout", r"shopify-payment-token",
        r"shopify.card", r"data-shopify-checkout",
        r"api.shopify.com/payments"
    ],
    "Worldpay": [
        r"secure.worldpay.com", r"worldpay.js", r"data-worldpay", r"worldpay-checkout",
        r"worldpay-payment-sdk", r"worldpay-secure", r"secure-test.worldpay.com",
        r"worldpay.min.js", r"worldpay.token", r"worldpay-payment-form",
        r"access.worldpay.com", r"worldpay-3ds", r"data-worldpay-token"
    ],
    "2Checkout": [
        r"www.2checkout.com", r"2co.js", r"data-2checkout", r"2checkout-payment",
        r"secure.2co.com", r"2checkout-hosted", r"api.2checkout.com", r"2co.min.js",
        r"2checkout.token", r"2co-checkout", r"data-2co-seller-id",
        r"2checkout.convertplus", r"secure.2co.com/v2"
    ],
    "Amazon Pay": [
        r"payments.amazon.com", r"amazonpay.js", r"data-amazon-pay", r"amazon-pay-button",
        r"amazon-pay-checkout-sdk", r"amazon-pay-wallet", r"amazon-checkout.js",
        r"payments.amazon.com/v2", r"amazon-pay-token", r"amazon-pay-sdk",
        r"data-amazon-pay-merchant-id", r"amazon-pay-signin", r"amazon-pay-checkout-session"
    ],
    "Apple Pay": [
        r"apple-pay.js", r"data-apple-pay", r"apple-pay-button", r"apple-pay-checkout-sdk",
        r"apple-pay-session", r"apple-pay-payment-request", r"ApplePaySession",
        r"apple-pay-merchant-id", r"apple-pay-payment", r"apple-pay-sdk",
        r"data-apple-pay-token", r"apple-pay-checkout", r"apple-pay-domain"
    ],
    "Google Pay": [
        r"pay.google.com", r"googlepay.js", r"data-google-pay", r"google-pay-button",
        r"google-pay-checkout-sdk", r"google-pay-tokenization", r"payments.googleapis.com",
        r"google.payments.api", r"google-pay-token", r"google-pay-payment-method",
        r"data-google-pay-merchant-id", r"google-pay-checkout", r"google-pay-sdk"
    ],
    "Mollie": [
        r"api.mollie.com", r"mollie.js", r"data-mollie", r"mollie-checkout",
        r"mollie-payment-sdk", r"mollie-components", r"mollie.min.js",
        r"profile.mollie.com", r"mollie-payment-token", r"mollie-create-payment",
        r"data-mollie-profile-id", r"mollie-checkout-form", r"mollie-redirect"
    ],
    "Opayo": [
        r"live.opayo.eu", r"opayo.js", r"data-opayo", r"opayo-checkout",
        r"opayo-payment-sdk", r"opayo-form", r"test.opayo.eu", r"opayo.min.js",
        r"opayo-payment-token", r"opayo-3ds", r"data-opayo-merchant-id",
        r"opayo-hosted", r"opayo.api"
    ],
    "Paddle": [
        r"checkout.paddle.com", r"paddle ‐button.js", r"paddle.js", r"data-paddle",
        r"paddle-checkout-sdk", r"paddle-product-id", r"api.paddle.com",
        r"paddle.min.js", r"paddle-checkout", r"data-paddle-vendor-id",
        r"paddle.Checkout.open", r"paddle-transaction-id", r"paddle-hosted"
    ],
    "3D Secure": [
        r"(?i)three_d_secure", r"supports3DS", r"3dsecure", r"three_d_secure_usage", r"request_three_d_secure", r"tdsecure", r"ThreeDSMethodTimeoutError", r"ThreeDSMethodFormError", r"SQUARE_3DS_IFRAME_TIMEOUT", r"three_ds_method_url_hostname", r"ThreeDSMethodError", r"ThreeDSMethodTransactionIdError",
        r"secure-auth", r"three_d", r"threeds", r"emv3ds", r"3d_secure_v2", r"3d_secure_2", r"securecode", r"3ds2", r"verifiedbyvisa", r"cardinalcommerce", r"3d-auth", r"3d[\s_-]?secure", r"cardinal.min.js", r"window.ThreeDS", r"stripe.com/3ds", r"3ds-container", r"secure-frame", r"secure-auth.*(payment|card|transaction)", r"(?i)securecode"
    ],
    # Captcha and Anti-Bot Patterns
    "reCaptcha": [
        r"g-recaptcha", r"recaptcha/api.js", r"data-sitekey", r"nocaptcha", r"enableRecaptcha", r"6L[0-9A-Za-z_-]{38}"
        r"recaptcha.net", r"www.google.com/recaptcha", r"grecaptcha.execute", r"google.com/recaptcha",
        r"grecaptcha.render", r"grecaptcha.ready", r"recaptcha-token"
    ],
    "hCaptcha": [
        r"hcaptcha", r"assets.hcaptcha.com", r"hcaptcha.com/1/api.js",
        r"data-hcaptcha-sitekey", r"js.stripe.com/v3/hcaptcha-invisible",
        r"hcaptcha-invisible", r"hcaptcha.execute"
    ],
    "Turnstile": [
        r"turnstile", r"challenges.cloudflare.com", r"cf-turnstile-response",
        r"data-sitekey", r"__cf_chl_", r"cf_clearance"
    ],
    "Arkose Labs": [
        r"arkose-labs", r"funcaptcha", r"client-api.arkoselabs.com",
        r"fc-token", r"fc-widget", r"arkose", r"press and hold", r"funcaptcha.com"
    ],
    "GeeTest": [
        r"geetest", r"gt_captcha_obj", r"gt.js", r"geetest_challenge",
        r"geetest_validate", r"geetest_seccode", r"geetest.com"
    ],
    "BotDetect": [
        r"botdetectcaptcha", r"BotDetect", r"BDC_CaptchaImage", r"CaptchaCodeTextBox"
    ],
    "KeyCAPTCHA": [
        r"keycaptcha", r"kc_submit", r"kc__widget", r"s_kc_cid"
    ],
    "Anti Bot Detection": [
        r"fingerprintjs", r"js.challenge", r"checking your browser",
        r"verify you are human", r"please enable javascript and cookies",
        r"sec-ch-ua-platform"
    ],
    "Captcha": [
        r"captcha-container", r"captcha-box", r"captcha-frame", r"captcha_input",
        r"id=captcha", r"class=captcha", r"data-captcha-sitekey"
    ],
    # E-commerce Platforms
    "Shopify": [
        r"shopify.com", r"data-shopify", r"hopify-buy.js", r"cdn.shopify.com", r"shopify-checkout-api",
        r"ShopifyAnalytics", r"myshopify.com", r"cdn.shopify.com"
    ],
    "WooCommerce": [
        r"woocommerce_params", r"wp-content/plugins/woocommerce", r"wc-ajax", r"woocommerce-checkout", r"wc_payment_method", r"woocommerce.min.js", r"woocommerce_order"
    ],
    "Magento": [
        r"mage/requirejs/mage", r"mage/requirejs/mage", r"Magento_", r"mage.cookies"
    ],
    "Wix": [
        r"wix.com", r"wixStores", r"shops.wixapps.net"
    ],
    "Squarespace": [
        r"squarespace.com", r"SquarespaceCommerce", r"static.squarespace.com"
    ],
    "PrestaShop": [
        r"PrestaShop", r"blockcart.js", r"ps_shoppingcart"
    ],
    "BigCommerce": [
        r"bigcommerce.com", r"stencil-utils", r"cdn.bcappsvc.com"
    ],
    "Cloudflare": [
        r"cloudflare.com", r"cf-ray", r"__cf_chl", r"checking your browser",
        r"cf-request-id", r"js.challenge", r"challenge-platform", r"challenges.cloudflare.com", r"cf-turnstile", r"cloudflareinsights.com", r"cdn.cloudflare.com", r"__cf_bm",
        r"cdn-cgi"
    ]
}
PAYMENT_GATEWAYS = [
    "Stripe", "PayPal", "Braintree", "Adyen", "Authorize.Net", "Square", "Klarna",
    "Checkout.com", "Razorpay", "Paytm", "Shopify Payments", "Worldpay", "2Checkout",
    "Amazon Pay", "Apple Pay", "Google Pay", "Mollie", "Opayo", "Paddle"
]
CAPTCHA_TYPES = [
    "reCaptcha", "hCaptcha", "Turnstile", "Arkose Labs", "GeeTest", "BotDetect",
    "KeyCAPTCHA", "Anti Bot Detection", "Captcha"
]
PLATFORMS = [
    "Shopify", "WooCommerce", "Magento", "Wix", "Squarespace", "PrestaShop", "BigCommerce"
]
SECURE_3D = ["3D Secure"]

async def deep_source_scan(url):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800},
            java_script_enabled=True
        )
        page = await context.new_page()

        print(f"☄️ Navigating to: {url}")
        collected_sources = {}

        async def handle_response(response):
            ct = response.headers.get("content-type", "")
            if any(t in ct for t in ["javascript", "html", "css", "json", "text"]):
                try:
                    body = await response.text()
                    collected_sources[response.url] = body
                except:
                    pass

        page.on("response", handle_response)

        try:
            await page.goto(url, timeout=60000, wait_until="load")
        except Exception as e:
            print(f"⚠️ Website too Heavy to Load: {e}")

        try:
            content = await page.content()
            collected_sources["inline:main"] = content
        except:
            pass

        for frame in page.frames:
            try:
                frame_content = await frame.content()
                collected_sources[f"iframe:{frame.url}"] = frame_content
            except:
                pass

        await browser.close()

        found_gateways = []
        found_cloudflare = "Not Found"
        found_captcha = []
        found_platforms = []
        found_3d_secure = "Not Found"

        print("\n⏳ Processing:")
        found = False
        for label, patterns in ALL_PATTERNS.items():
            for pattern in patterns:
                regex = re.compile(pattern, re.IGNORECASE)
                for src_url, code in collected_sources.items():
                    matches = list(regex.finditer(code))
                    for match in matches:
                        found = True
                        snippet = code[match.start()-30:match.end()+30].replace('\n', ' ')
                        print(f"✅ [{label}] Found '{pattern}' in: {src_url}")
                        print(f"   ➜ Snippet: ...{snippet}...\n")
                        if label in PAYMENT_GATEWAYS and label not in found_gateways:
                            found_gateways.append(label)
                        elif label == "Cloudflare":
                            found_cloudflare = "Found"
                        elif label in CAPTCHA_TYPES and label not in found_captcha:
                            found_captcha.append(label)
                        elif label in PLATFORMS and label not in found_platforms:
                            found_platforms.append(label)
                        elif label in SECURE_3D:
                            found_3d_secure = "Found"

        if not found:
            print("❌ Nothing Found, What a dumb site.")

        # Return results in the exact format you specified
        result = {
            "URL": url,
            "Gateway": ", ".join(found_gateways) if found_gateways else "None",
            "Cloudflare": found_cloudflare,
            "Captcha": ", ".join(found_captcha) if found_captcha else "Not Found",
            "Platform": ", ".join(found_platforms) if found_platforms else "None",
            "3D Secure": found_3d_secure
        }
        return result

@app.get("/gate/")
async def scan_url(url: str):
    """
    API endpoint to scan a provided URL for payment gateways, captchas, platforms, and 3D Secure.
    Usage: /gate/?url=<website_url>
    """
    if not url:
        raise HTTPException(status_code=400, detail="URL parameter is required")
    
    # Ensure URL starts with http:// or https://
    if not url.startswith(("http://", "https://")):
        url = f"https://{url}"
    
    try:
        result = await deep_source_scan(url)
        return JSONResponse(content=result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error scanning URL: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
