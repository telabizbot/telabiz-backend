from fastapi import FastAPI, Request, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import os
import json
import httpx
import re
import jwt
import hmac
import hashlib
import urllib.parse
from datetime import datetime, timedelta
from dotenv import load_dotenv
from slowapi import Limiter
from slowapi.util import get_remote_address
from cryptography.fernet import Fernet

load_dotenv()

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)
security = HTTPBearer()
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# ---------- CONFIG ----------
SECRET_KEY = os.getenv('SECRET_KEY', 'your_secret_key_change_me')
BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
ENCRYPTION_KEY = os.getenv('ENCRYPTION_KEY')
if ENCRYPTION_KEY:
    cipher = Fernet(ENCRYPTION_KEY)

# ---------- JWT ----------
def create_jwt(user_data: dict) -> str:
    payload = {**user_data, 'exp': datetime.utcnow() + timedelta(hours=24)}
    return jwt.encode(payload, SECRET_KEY, algorithm='HS256')

def verify_jwt(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=['HS256'])
        return payload
    except:
        raise HTTPException(status_code=401, detail="Invalid token")

# ---------- TELEGRAM INITDATA ----------
def verify_telegram_init_data(init_data: str) -> dict:
    parsed = urllib.parse.parse_qs(init_data)
    received_hash = parsed.pop('hash', [None])[0]
    if not received_hash:
        raise ValueError("Missing hash")
    sorted_keys = sorted(parsed.keys())
    data_string = "\n".join(f"{key}={parsed[key][0]}" for key in sorted_keys)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    expected_hash = hmac.new(secret_key, data_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(received_hash, expected_hash):
        raise ValueError("Invalid signature")
    return {k: v[0] for k, v in parsed.items()}

# ---------- PRICING ----------
class PricingManager:
    def __init__(self):
        self.total_merchants = 0
    
    def get_plan_price(self, plan_name):
        plans = {
            'pro': {'founder': 7000, 'early': 12500, 'regular': 25000},
            'business': {'founder': 25000, 'early': 42500, 'regular': 85000}
        }
        merchant_count = self.total_merchants
        if merchant_count <= 500:
            tier = 'founder'
        elif merchant_count <= 2000:
            tier = 'early'
        else:
            tier = 'regular'
        return plans.get(plan_name, {}).get(tier, 0)

pricing = PricingManager()

# ---------- SMART TEMPLATES ----------
SMART_TEMPLATES = {
    "Agbada": {"prompt": "A stunning {color} Agbada, {style} fashion design, {background} background, professional fashion photography, high quality, 4k", "negative": "blurry"},
    "Dress": {"prompt": "Elegant {color} dress, {style} silhouette, {background} background, fashion editorial, professional lighting, high resolution", "negative": "wrinkled"},
    "Shoe": {"prompt": "Premium {color} shoes, {style} design, {background} background, product photography, commercial style, 8k", "negative": "scuffed"},
    "Bag": {"prompt": "Luxury {color} bag, {style} craftsmanship, {background} background, studio lighting, high-end fashion, detailed, 4k", "negative": "cheap"}
}

# ---------- HELPERS ----------
async def send_telegram(chat_id: int, text: str, parse_mode='Markdown'):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": parse_mode})

async def parse_with_cloudflare(text: str) -> dict:
    cf_token = os.getenv('CLOUDFLARE_API_TOKEN')
    cf_account = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    prompt = f"""Parse this business note. Return ONLY valid JSON. Extract: client_name (string), product (string), total_amount (number), deposit (number), deadline (string if mentioned). Note: "{text}" """
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/run/@cf/meta/llama-3-8b-instruct", headers={"Authorization": f"Bearer {cf_token}"}, json={"prompt": prompt, "max_tokens": 200})
        result = resp.json()
        raw = result.get('result', {}).get('response', '{}')
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        data = json.loads(match.group()) if match else {}
    total = float(data.get('total_amount', 0))
    deposit = float(data.get('deposit', 0))
    balance = total - deposit
    return {'client': data.get('client_name', 'Unknown'), 'product': data.get('product', 'Unknown'), 'total_amount': total, 'deposit': deposit, 'balance': balance, 'is_valid': balance >= 0, 'human_readable': f"Total: ₦{total:,.2f} - Deposit: ₦{deposit:,.2f} = Balance: ₦{balance:,.2f}", 'deadline': data.get('deadline', 'Not set')}

# ---------- TELEGRAM WEBHOOK ----------
@app.post("/webhook")
@limiter.limit("10/minute")
async def telegram_webhook(request: Request):
    data = await request.json()
    if "message" in data:
        msg = data["message"]
        text = msg.get("text", "")
        chat_id = msg["chat"]["id"]

        if text == "/start":
            await send_telegram(chat_id, "👋 Welcome to TelaBiz!\n\n🔹 Try: `Sold Agbada to Tunde for 90k, received 40k`\n🔹 Open Mini App: tap the menu button\n🔹 Help: /help\n🔹 Pricing: /pricing\n🔹 Community: /community")
            return {"ok": True}

        if text.lower() in ["/help", "help"]:
            await send_telegram(chat_id, "📚 TelaBiz Help\n\n• Type a sale: `Sold X to Y for Z, received deposit`\n• /pricing - See plans\n• /community - Join community\n• Support: type 'Talk to human'")
            return {"ok": True}

        if text.lower() in ["/pricing", "pricing"]:
            pro_price = pricing.get_plan_price('pro')
            business_price = pricing.get_plan_price('business')
            await send_telegram(chat_id, f"💎 TelaBiz Pricing\n\nPro: ₦{pro_price:,}/month\nBusiness: ₦{business_price:,}/month\n\nFree: ₦0/month (50 transactions)")
            return {"ok": True}

        if text.lower() in ["/community", "community"]:
            await send_telegram(chat_id, "🌐 TelaBiz Community\n\n📢 Channel: @TelaBizChannel\n💬 Merchant Group: @TelaBizCommunity\n🛍️ Buyer Group: @TelaBizBuyers")
            return {"ok": True}

        if any(k in text.lower() for k in ["sold", "received", "deposit"]):
            parsed = await parse_with_cloudflare(text)
            await send_telegram(chat_id, f"📊 Transaction Preview\n\n{parsed['human_readable']}\n\n👤 Client: {parsed['client']}\n📦 Product: {parsed['product']}\n📅 Deadline: {parsed['deadline']}")
            return {"ok": True}

        if "talk to human" in text.lower():
            support_group = os.getenv('SUPPORT_GROUP_ID')
            if support_group:
                await send_telegram(support_group, f"🆘 SUPPORT REQUEST\n\nUser: {msg['from']['first_name']}\nID: {chat_id}\nMessage: {text}")
            await send_telegram(chat_id, "👋 I've notified our support team. You'll get a reply within 24 hours.")
            return {"ok": True}

        faq = {"cost": "TelaBiz free for 50 transactions/mo. Pro starts at ₦7,000/mo.", "price": "TelaBiz free for 50 transactions/mo. Pro starts at ₦7,000/mo.", "free": "TelaBiz free for 50 transactions/mo.", "offline": "Yes, works offline. Data syncs when online.", "payment": "Cards via Paystack & Mobile Money via Flutterwave."}
        for key, value in faq.items():
            if key in text.lower():
                await send_telegram(chat_id, value)
                return {"ok": True}
        await send_telegram(chat_id, "I'm not sure. Type 'Talk to human' for help.")
    return {"ok": True}

# ---------- API ENDPOINTS ----------
@app.post("/api/auth")
@limiter.limit("10/minute")
async def authenticate(request: Request):
    init_data = request.headers.get('X-Telegram-Init-Data')
    if not init_data:
        raise HTTPException(status_code=401, detail="Missing authentication")
    try:
        user_data = verify_telegram_init_data(init_data)
        jwt_token = create_jwt({'user_id': user_data.get('id'), 'username': user_data.get('username'), 'role': 'merchant'})
        return {"token": jwt_token, "user": user_data}
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid authentication")

@app.post("/parse")
@limiter.limit("30/minute")
async def parse_text(request: Request, user=Depends(verify_jwt)):
    data = await request.json()
    return await parse_with_cloudflare(data.get("text", ""))

@app.post("/api/transactions")
@limiter.limit("30/minute")
async def save_transaction(request: Request, user=Depends(verify_jwt)):
    data = await request.json()
    print(f"📦 Transaction saved: {data}")
    return {"status": "ok"}

@app.post("/generate-smart-image")
@limiter.limit("5/minute")
async def generate_smart_image(request: Request, user=Depends(verify_jwt)):
    data = await request.json()
    product_type = data.get('product_type', 'Custom')
    color = data.get('color', '')
    style = data.get('style', '')
    background = data.get('background', '')
    custom_prompt = data.get('custom_prompt', '')

    if product_type == 'Custom' and custom_prompt:
        prompt = f"{custom_prompt}, professional, high quality, studio lighting, 4k"
    else:
        template = SMART_TEMPLATES.get(product_type, SMART_TEMPLATES["Agbada"])
        prompt = template["prompt"].format(color=color or "beautiful", style=style or "modern", background=background or "studio")

    cf_token = os.getenv('CLOUDFLARE_API_TOKEN')
    cf_account = os.getenv('CLOUDFLARE_ACCOUNT_ID')
    async with httpx.AsyncClient() as client:
        resp = await client.post(f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/run/@cf/black-forest-labs/flux-1-schnell", headers={"Authorization": f"Bearer {cf_token}"}, json={"prompt": prompt})
        image_b64 = resp.json().get('result', {}).get('image')
        return {"image": image_b64, "prompt_used": prompt}

@app.get("/api/prices")
async def get_prices():
    return {"pro": {"founder": pricing.get_plan_price('pro'), "early": pricing.get_plan_price('pro'), "regular": pricing.get_plan_price('pro')}, "business": {"founder": pricing.get_plan_price('business'), "early": pricing.get_plan_price('business'), "regular": pricing.get_plan_price('business')}}

@app.post("/paystack-webhook")
async def paystack_webhook(request: Request):
    raw_body = await request.body()
    data = json.loads(raw_body)
    if data.get('event') == 'charge.success':
        print(f"✅ Paystack: ₦{data['data']['amount']/100} | Ref: {data['data']['reference']}")
    return {"status": "ok"}

@app.post("/flutterwave-webhook")
async def flutterwave_webhook(request: Request):
    raw_body = await request.body()
    data = json.loads(raw_body)
    if data.get('status') == 'successful':
        print(f"✅ Flutterwave: ₦{data['amount']} | Ref: {data['tx_ref']}")
    return {"status": "ok"}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
