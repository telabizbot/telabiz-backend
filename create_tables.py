import asyncpg
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS merchants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_user_id BIGINT UNIQUE NOT NULL,
            business_name TEXT,
            phone TEXT,
            email TEXT,
            bank_name TEXT,
            account_number TEXT,
            verification_level TEXT DEFAULT 'basic',
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS customers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id UUID REFERENCES merchants(id),
            name TEXT,
            phone TEXT,
            email TEXT,
            measurements JSONB,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS transactions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id UUID REFERENCES merchants(id),
            customer_id UUID REFERENCES customers(id),
            amount NUMERIC,
            type TEXT,
            status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id UUID REFERENCES merchants(id),
            name TEXT,
            description TEXT,
            price NUMERIC,
            category TEXT,
            stock INTEGER DEFAULT 0,
            images JSONB,
            variations JSONB,
            status TEXT DEFAULT 'draft',
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS debts (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id UUID REFERENCES merchants(id),
            customer_id UUID REFERENCES customers(id),
            total_owed NUMERIC,
            amount_paid NUMERIC DEFAULT 0,
            balance NUMERIC DEFAULT 0,
            status TEXT DEFAULT 'active',
            due_date DATE,
            created_at TIMESTAMP DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            merchant_id UUID REFERENCES merchants(id),
            plan TEXT,
            status TEXT DEFAULT 'active',
            start_date TIMESTAMP DEFAULT NOW(),
            end_date TIMESTAMP
        );
        ALTER TABLE customers ENABLE ROW LEVEL SECURITY;
        ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
        ALTER TABLE products ENABLE ROW LEVEL SECURITY;
        ALTER TABLE debts ENABLE ROW LEVEL SECURITY;
        CREATE POLICY merchant_isolation_customers ON customers
            USING (merchant_id = current_setting('app.current_merchant_id')::uuid);
        CREATE POLICY merchant_isolation_transactions ON transactions
            USING (merchant_id = current_setting('app.current_merchant_id')::uuid);
        CREATE POLICY merchant_isolation_products ON products
            USING (merchant_id = current_setting('app.current_merchant_id')::uuid);
        CREATE POLICY merchant_isolation_debts ON debts
            USING (merchant_id = current_setting('app.current_merchant_id')::uuid);
    ''')
    await conn.close()
    print("Tables created and RLS enabled")

asyncio.run(main())
