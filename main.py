from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import httpx
import re
import asyncpg
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------- DATABASE ----------
async def get_db():
    return await asyncpg.connect(os.getenv("DATABASE_URL"))

# ---------- SEND TELEGRAM WITH BUTTONS ----------
async def send_telegram(chat_id: int, text: str, reply_markup=None):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if reply_markup:
        payload["reply_markup"] = reply_markup
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)

def make_buttons(buttons: list):
    keyboard = []
    for row in buttons:
        if len(row) == 2:
            text, action = row
            if action.startswith("http"):
                btn = {"text": text, "url": action}
            else:
                btn = {"text": text, "callback_data": action}
            keyboard.append([btn])
    return json.dumps({"inline_keyboard": keyboard})

# ---------- SMART PARSING ----------
async def parse_with_cloudflare(text: str) -> dict:
    # Clean text
    text = text.replace(',', '')
    
    # Handle "k" (thousand) conversion
    total_match = re.search(r'(\d+[.,]?\d*)\s*k?', text, re.IGNORECASE)
    deposit_match = re.search(r'(?:received|paid|deposit|pay)\s*(\d+[.,]?\d*)\s*k?', text, re.IGNORECASE)
    
    total = float(total_match.group(1)) if total_match else 0
    deposit = float(deposit_match.group(1)) if deposit_match else 0
    
    # If "k" appears after number, multiply by 1000
    if total_match and 'k' in text[total_match.start():total_match.end()]:
        total = total * 1000
    if deposit_match and 'k' in text[deposit_match.start():deposit_match.end()]:
        deposit = deposit * 1000
    
    balance = total - deposit
    
    # Find client name
    client_match = re.search(r'(?:to|for|with)\s+([A-Za-z]+)', text, re.IGNORECASE)
    client = client_match.group(1) if client_match else 'Unknown'
    
    # Find product
    product_match = re.search(r'(?:sold|bought|purchased)\s+([A-Za-z\s]+?)(?:\s+to|\s+for|\s+$)', text, re.IGNORECASE)
    product = product_match.group(1).strip() if product_match else 'Unknown'
    
    return {
        'client': client,
        'product': product,
        'total_amount': total,
        'deposit': deposit,
        'balance': balance,
        'is_valid': balance >= 0,
        'human_readable': f"Total: ₦{total:,.2f} - Deposit: ₦{deposit:,.2f} = Balance: ₦{balance:,.2f}",
        'deadline': 'Not set'
    }

# Store transaction data temporarily (in memory)
pending_transactions = {}

# ---------- TELEGRAM WEBHOOK ----------
@app.post("/webhook")
async def telegram_webhook(request: Request):
    data = await request.json()
    
    # Handle callback queries (button clicks)
    if "callback_query" in data:
        callback = data["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        data_type = callback["data"]
        message_id = callback["message"]["message_id"]
        
        if data_type == "save_transaction":
            await send_telegram(chat_id, "✅ *Transaction saved successfully!*")
        elif data_type == "edit_transaction":
            await send_telegram(chat_id, "✏️ Please reply with the corrected transaction details.")
        elif data_type == "cancel_transaction":
            await send_telegram(chat_id, "❌ Transaction cancelled.")
        elif data_type == "products":
            await send_telegram(chat_id, "📦 *Your Products:*\n\nYou have no products yet.")
        elif data_type == "debts":
            await send_telegram(chat_id, "💰 *Your Outstanding Debts:*\n\n🎉 No outstanding debts!")
        elif data_type == "pricing":
            await send_telegram(chat_id, """
💎 *TelaBiz Pricing*

*🚀 Pro* – ₦7,000/month
✅ Unlimited transactions
✅ Advanced AI images

*💼 Business* – ₦25,000/month
✅ Everything in Pro
✅ Supplier marketplace

*🆓 Free* – ₦0/month
50 transactions • Basic AI images
""")
        elif data_type == "community":
            await send_telegram(chat_id, """
🌐 *TelaBiz Community*

📢 Channel: @TelaBizChannel
💬 Merchant Group: @TelaBizCommunity
🛍️ Buyer Group: @TelaBizBuyers
""")
        return {"ok": True}
    
    # Handle regular messages
    if "message" in data:
        msg = data["message"]
        text = msg.get("text", "")
        chat_id = msg["chat"]["id"]

        # ---------- COMMANDS ----------
        if text == "/start":
            buttons = make_buttons([
                ["📱 Open App", "https://telabiz-frontend.vercel.app"],
                ["📦 Products", "products"],
                ["💰 Debts", "debts"]
            ])
            await send_telegram(chat_id, """
👋 *Welcome to TelaBiz!*

Your business OS inside Telegram.

🔹 *Try:* `Sold Agbada to Tunde for 90k, received 40k`
🔹 *Commands:* /help, /pricing, /community, /products, /debts

*Start growing your business today!* 🚀
""", reply_markup=buttons)
            return {"ok": True}

        if text.lower() in ["/help", "help"]:
            buttons = make_buttons([
                ["📱 Open App", "https://telabiz-frontend.vercel.app"],
                ["💎 Pricing", "pricing"],
                ["🌐 Community", "community"]
            ])
            await send_telegram(chat_id, """
📚 *TelaBiz Help*

*Commands:*
• /start - Welcome
• /help - This help
• /pricing - View plans
• /community - Join community
• /products - View products
• /debts - View debts

*Quick Start:*
Type: `Sold Agbada to Tunde for 90k, received 40k`

*Support:*
Type "Talk to human"
""", reply_markup=buttons)
            return {"ok": True}

        if text.lower() in ["/pricing", "pricing"]:
            buttons = make_buttons([
                ["🔒 Subscribe to Pro", "#"],
                ["🔒 Subscribe to Business", "#"]
            ])
            await send_telegram(chat_id, """
💎 *TelaBiz Pricing*

*🚀 Pro* – ₦7,000/month
✅ Unlimited transactions
✅ Advanced AI images
✅ Video loops
✅ Analytics

*💼 Business* – ₦25,000/month
✅ Everything in Pro
✅ Supplier marketplace
✅ Team accounts
✅ Custom branding

*🆓 Free* – ₦0/month
50 transactions • Basic AI images • Basic storefront
""", reply_markup=buttons)
            return {"ok": True}

        if text.lower() in ["/community", "community"]:
            buttons = make_buttons([
                ["📢 Join Channel", "https://t.me/TelaBizChannel"],
                ["💬 Join Merchant Group", "https://t.me/TelaBizCommunity"],
                ["🛍️ Join Buyer Group", "https://t.me/TelaBizBuyers"]
            ])
            await send_telegram(chat_id, """
🌐 *TelaBiz Community*

Join thousands of merchants growing together!

📢 *Channel:* @TelaBizChannel
💬 *Merchant Group:* @TelaBizCommunity
🛍️ *Buyer Group:* @TelaBizBuyers

Tap a button below to join! 🚀
""", reply_markup=buttons)
            return {"ok": True}

        if text.lower() in ["/products", "products"]:
            await send_telegram(chat_id, "📦 *Your Products:*\n\nYou have no products yet. Add them in the Mini App.")
            return {"ok": True}

        if text.lower() in ["/debts", "debts"]:
            await send_telegram(chat_id, "💰 *Your Outstanding Debts:*\n\n🎉 No outstanding debts! Great job!")
            return {"ok": True}

        # ---------- SMART SALE DETECTION ----------
        if any(k in text.lower() for k in ["sold", "received", "deposit", "pay", "bought", "purchased"]):
            parsed = await parse_with_cloudflare(text)
            buttons = make_buttons([
                ["✅ Save", "save_transaction"],
                ["✏️ Edit", "edit_transaction"],
                ["❌ Cancel", "cancel_transaction"]
            ])
            await send_telegram(chat_id, f"""
📊 *Transaction Preview*

{parsed['human_readable']}

👤 *Client:* {parsed['client']}
📦 *Product:* {parsed['product']}
📅 *Deadline:* {parsed['deadline']}

Tap a button below:
""", reply_markup=buttons)
            return {"ok": True}

        # ---------- FAQ ----------
        faq = {"cost": "TelaBiz free for 50 transactions/mo. Pro starts at ₦7,000/mo.", "price": "TelaBiz free for 50 transactions/mo.", "offline": "Yes, works offline. Data syncs when online.", "payment": "Cards via Paystack & Mobile Money via Flutterwave."}
        for key, value in faq.items():
            if key in text.lower():
                await send_telegram(chat_id, value)
                return {"ok": True}
        
        # ---------- TALK TO HUMAN ----------
        if "talk to human" in text.lower():
            support_group = os.getenv('SUPPORT_GROUP_ID')
            if support_group:
                await send_telegram(support_group, f"🆘 SUPPORT REQUEST\n\nUser: {msg['from']['first_name']}\nID: {chat_id}\nMessage: {text}")
            await send_telegram(chat_id, "👋 I've notified our support team. You'll get a reply within 24 hours.")
            return {"ok": True}

        await send_telegram(chat_id, "I'm not sure. Type 'Talk to human' for help.")
    return {"ok": True}

# ---------- API ENDPOINTS ----------
@app.post("/parse")
async def parse_text(request: Request):
    data = await request.json()
    return await parse_with_cloudflare(data.get("text", ""))

@app.post("/api/transactions")
async def save_transaction(request: Request):
    data = await request.json()
    print(f"📦 Transaction saved: {data}")
    return {"status": "success", "message": "Transaction saved!"}

@app.post("/generate-smart-image")
async def generate_smart_image(request: Request):
    data = await request.json()
    product_type = data.get('product_type', 'Custom')
    color = data.get('color', '')
    style = data.get('style', '')
    background = data.get('background', '')
    custom_prompt = data.get('custom_prompt', '')

    SMART_TEMPLATES = {
        "Agbada": {"prompt": "A stunning {color} Agbada, {style} fashion design, {background} background, professional fashion photography, high quality, 4k"},
        "Dress": {"prompt": "Elegant {color} dress, {style} silhouette, {background} background, fashion editorial, professional lighting, high resolution"},
        "Shoe": {"prompt": "Premium {color} shoes, {style} design, {background} background, product photography, commercial style, 8k"},
        "Bag": {"prompt": "Luxury {color} bag, {style} craftsmanship, {background} background, studio lighting, high-end fashion, detailed, 4k"}
    }

    if product_type == 'Custom' and custom_prompt:
        prompt = f"{custom_prompt}, professional, high quality, studio lighting, 4k"
    else:
        template = SMART_TEMPLATES.get(product_type, SMART_TEMPLATES["Agbada"])
        prompt = template["prompt"].format(color=color or "beautiful", style=style or "modern", background=background or "studio")

    cf_token = os.getenv('CLOUDFLARE_API_TOKEN')
    cf_account = os.getenv('CLOUDFLARE_ACCOUNT_ID')

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.cloudflare.com/client/v4/accounts/{cf_account}/ai/run/@cf/black-forest-labs/flux-1-schnell",
            headers={"Authorization": f"Bearer {cf_token}"},
            json={"prompt": prompt}
        )
        image_b64 = resp.json().get('result', {}).get('image')
        return {"image": image_b64, "prompt_used": prompt}

@app.get("/health")
async def health():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

@app.get("/")
async def root():
    return {"message": "TelaBiz Backend is running!", "status": "ok"}

# ---------- PRICES ----------
@app.get("/api/prices")
async def get_prices():
    return {
        "pro": {"founder": 7000, "early": 12500, "regular": 25000},
        "business": {"founder": 25000, "early": 42500, "regular": 85000}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
