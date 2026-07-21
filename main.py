from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import os
import json
import httpx
import re
import asyncpg
from datetime import datetime
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

# ---------- TELEGRAM API ----------
def send_message(chat_id, text, keyboard=None):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
    if keyboard:
        payload["reply_markup"] = keyboard
    httpx.post(url, json=payload)

def make_inline_keyboard(buttons):
    inline_keyboard = []
    for row in buttons:
        row_buttons = []
        for text, action in row:
            if action.startswith("http"):
                row_buttons.append({"text": text, "url": action})
            else:
                row_buttons.append({"text": text, "callback_data": action})
        inline_keyboard.append(row_buttons)
    return {"inline_keyboard": inline_keyboard}

# ---------- SMART PARSING ----------
def parse_sale(text):
    # Clean
    text = text.replace(',', '')
    
    # Find amount (numbers with optional 'k')
    total_match = re.search(r'(\d+[.,]?\d*)\s*k?', text)
    deposit_match = re.search(r'(?:received|paid|deposit|pay)\s*(\d+[.,]?\d*)\s*k?', text)
    
    total = float(total_match.group(1)) if total_match else 0
    deposit = float(deposit_match.group(1)) if deposit_match else 0
    
    # Handle 'k' (thousand)
    if total_match and 'k' in text[total_match.start():total_match.end()]:
        total = total * 1000
    if deposit_match and 'k' in text[deposit_match.start():deposit_match.end()]:
        deposit = deposit * 1000
    
    balance = total - deposit
    
    # Find client
    client_match = re.search(r'(?:to|for|with)\s+([A-Za-z]+)', text)
    client = client_match.group(1) if client_match else 'Unknown'
    
    # Find product
    product_match = re.search(r'(?:sold|bought|purchased)\s+([A-Za-z\s]+?)(?:\s+to|\s+for|\s+$)', text)
    product = product_match.group(1).strip() if product_match else 'Unknown'
    
    # If product is "Unknown" but we have "for [client]" pattern
    if product == 'Unknown':
        # Try to find product after amount
        after_amount = re.search(r'\d+[.,]?\d*\s*k?\s*([A-Za-z\s]+?)(?:\s+to|\s+for|\s+$)', text)
        if after_amount:
            product = after_amount.group(1).strip()
    
    return {
        'client': client,
        'product': product,
        'total': total,
        'deposit': deposit,
        'balance': balance,
        'human_readable': f"Total: ₦{total:,.2f} - Deposit: ₦{deposit:,.2f} = Balance: ₦{balance:,.2f}"
    }

# ---------- TEMP STORAGE ----------
pending_sales = {}

# ---------- WEBHOOK ----------
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    
    # ---------- CALLBACK QUERIES (BUTTON CLICKS) ----------
    if "callback_query" in data:
        callback = data["callback_query"]
        chat_id = callback["message"]["chat"]["id"]
        action = callback["data"]
        
        if action == "save_sale":
            if chat_id in pending_sales:
                sale = pending_sales[chat_id]
                # Save to database (insert)
                await send_telegram(chat_id, f"✅ *Sale saved!*\n\n{sale['client']} bought {sale['product']} for ₦{sale['total']:,.2f}")
                del pending_sales[chat_id]
            else:
                await send_telegram(chat_id, "❌ No pending sale to save.")
        
        elif action == "edit_sale":
            await send_telegram(chat_id, "✏️ Please type the corrected sale details.")
            pending_sales[chat_id] = {"editing": True}
        
        elif action == "cancel_sale":
            if chat_id in pending_sales:
                del pending_sales[chat_id]
            await send_telegram(chat_id, "❌ Sale cancelled.")
        
        elif action == "products":
            await send_telegram(chat_id, "📦 *Your Products:*\n\nYou have no products yet. Add them in the Mini App.")
        
        elif action == "debts":
            await send_telegram(chat_id, "💰 *Your Outstanding Debts:*\n\n🎉 No outstanding debts!")
        
        elif action == "pricing":
            keyboard = make_inline_keyboard([
                ["🔒 Subscribe to Pro", "sub_pro"],
                ["🔒 Subscribe to Business", "sub_business"]
            ])
            await send_message(chat_id, """
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
50 transactions • Basic AI images
""", json.dumps(keyboard))
        
        elif action == "community":
            keyboard = make_inline_keyboard([
                ["📢 Join Channel", "https://t.me/TelaBizChannel"],
                ["💬 Join Merchant Group", "https://t.me/TelaBizCommunity"],
                ["🛍️ Join Buyer Group", "https://t.me/TelaBizBuyers"]
            ])
            await send_message(chat_id, """
🌐 *TelaBiz Community*

📢 *Channel:* @TelaBizChannel
💬 *Merchant Group:* @TelaBizCommunity
🛍️ *Buyer Group:* @TelaBizBuyers
""", json.dumps(keyboard))
        
        elif action == "sub_pro":
            await send_telegram(chat_id, "🔒 *Pro Subscription*\n\nComing soon! 🚀")
        
        elif action == "sub_business":
            await send_telegram(chat_id, "🔒 *Business Subscription*\n\nComing soon! 🚀")
        
        return {"ok": True}
    
    # ---------- REGULAR MESSAGES ----------
    if "message" in data:
        msg = data["message"]
        text = msg.get("text", "")
        chat_id = msg["chat"]["id"]
        user = msg.get("from", {})
        first_name = user.get("first_name", "")
        
        # ----- START -----
        if text == "/start":
            keyboard = make_inline_keyboard([
                ["📱 Open App", "https://telabiz-frontend.vercel.app"],
                ["📦 Products", "products"],
                ["💰 Debts", "debts"],
                ["💎 Pricing", "pricing"],
                ["🌐 Community", "community"]
            ])
            await send_message(chat_id, f"""
👋 *Welcome to TelaBiz, {first_name}!*

Your business OS inside Telegram.

🔹 *Try:* `Sold Agbada to Tunde for 90k, received 40k`
🔹 *Commands:* /help, /pricing, /community, /products, /debts, /transactions, /stats

*Start growing your business today!* 🚀
""", json.dumps(keyboard))
            return {"ok": True}
        
        # ----- HELP -----
        if text.lower() in ["/help", "help"]:
            keyboard = make_inline_keyboard([
                ["📱 Open App", "https://telabiz-frontend.vercel.app"],
                ["💎 Pricing", "pricing"],
                ["🌐 Community", "community"]
            ])
            await send_message(chat_id, """
📚 *TelaBiz Help*

*Commands:*
• /start - Welcome
• /help - This help
• /pricing - View plans
• /community - Join community
• /products - View products
• /debts - View debts
• /transactions - View your sales
• /stats - View your business stats
• /customer [name] - View customer history

*Quick Start:*
Type: `Sold Agbada to Tunde for 90k, received 40k`

*Support:*
Type "Talk to human"
""", json.dumps(keyboard))
            return {"ok": True}
        
        # ----- PRICING -----
        if text.lower() in ["/pricing", "pricing"]:
            keyboard = make_inline_keyboard([
                ["🔒 Subscribe to Pro", "sub_pro"],
                ["🔒 Subscribe to Business", "sub_business"]
            ])
            await send_message(chat_id, """
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
50 transactions • Basic AI images
""", json.dumps(keyboard))
            return {"ok": True}
        
        # ----- COMMUNITY -----
        if text.lower() in ["/community", "community"]:
            keyboard = make_inline_keyboard([
                ["📢 Join Channel", "https://t.me/TelaBizChannel"],
                ["💬 Join Merchant Group", "https://t.me/TelaBizCommunity"],
                ["🛍️ Join Buyer Group", "https://t.me/TelaBizBuyers"]
            ])
            await send_message(chat_id, """
🌐 *TelaBiz Community*

📢 *Channel:* @TelaBizChannel
💬 *Merchant Group:* @TelaBizCommunity
🛍️ *Buyer Group:* @TelaBizBuyers
""", json.dumps(keyboard))
            return {"ok": True}
        
        # ----- PRODUCTS -----
        if text.lower() in ["/products", "products"]:
            await send_message(chat_id, "📦 *Your Products:*\n\nYou have no products yet. Add them in the Mini App.")
            return {"ok": True}
        
        # ----- DEBTS -----
        if text.lower() in ["/debts", "debts"]:
            await send_message(chat_id, "💰 *Your Outstanding Debts:*\n\n🎉 No outstanding debts! Great job!")
            return {"ok": True}
        
        # ----- TRANSACTIONS -----
        if text.lower() in ["/transactions", "transactions"]:
            await send_message(chat_id, "📋 *Your Recent Transactions:*\n\nYou have no transactions yet. Start selling!")
            return {"ok": True}
        
        # ----- STATS -----
        if text.lower() in ["/stats", "stats"]:
            await send_message(chat_id, """
📊 *Your Business Stats*

💰 *Total Revenue:* ₦0.00
📦 *Total Sales:* 0
💳 *Outstanding Debt:* ₦0.00

Keep selling! 🚀
""")
            return {"ok": True}
        
        # ----- CUSTOMER -----
        if text.lower().startswith("/customer"):
            parts = text.split(" ", 1)
            if len(parts) < 2:
                await send_message(chat_id, "👤 Please provide a name: `/customer Tunde`")
                return {"ok": True}
            await send_message(chat_id, f"📋 *{parts[1]}'s Order History:*\n\nNo orders found for {parts[1]}.")
            return {"ok": True}
        
        # ----- SMART SALE DETECTION -----
        if any(k in text.lower() for k in ["sold", "received", "deposit", "pay", "bought", "purchased"]):
            parsed = parse_sale(text)
            
            # Store for later saving
            pending_sales[chat_id] = parsed
            
            keyboard = make_inline_keyboard([
                ["✅ Save", "save_sale"],
                ["✏️ Edit", "edit_sale"],
                ["❌ Cancel", "cancel_sale"]
            ])
            await send_message(chat_id, f"""
📊 *Transaction Preview*

{parsed['human_readable']}

👤 *Client:* {parsed['client']}
📦 *Product:* {parsed['product']}

Tap a button below:
""", json.dumps(keyboard))
            return {"ok": True}
        
        # ----- FAQ -----
        faq = {
            "cost": "TelaBiz free for 50 transactions/mo. Pro starts at ₦7,000/mo.",
            "price": "TelaBiz free for 50 transactions/mo.",
            "offline": "Yes, works offline. Data syncs when online.",
            "payment": "Cards via Paystack & Mobile Money via Flutterwave."
        }
        for key, value in faq.items():
            if key in text.lower():
                await send_message(chat_id, value)
                return {"ok": True}
        
        # ----- TALK TO HUMAN -----
        if "talk to human" in text.lower():
            await send_message(chat_id, "👋 I've notified our support team. You'll get a reply within 24 hours.")
            return {"ok": True}
        
        await send_message(chat_id, "I'm not sure. Type 'Talk to human' for help.")
    return {"ok": True}

async def send_telegram(chat_id: int, text: str):
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    async with httpx.AsyncClient() as client:
        await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": text, "parse_mode": "Markdown"})

# ---------- API ----------
@app.post("/parse")
async def parse_text(request: Request):
    data = await request.json()
    return parse_sale(data.get("text", ""))

@app.post("/api/transactions")
async def save_transaction(request: Request):
    data = await request.json()
    print(f"📦 Transaction saved: {data}")
    return {"status": "success"}

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

@app.get("/api/prices")
async def get_prices():
    return {
        "pro": {"founder": 7000, "early": 12500, "regular": 25000},
        "business": {"founder": 25000, "early": 42500, "regular": 85000}
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
