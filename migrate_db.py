import asyncpg
import os
import asyncio
from dotenv import load_dotenv

load_dotenv()

async def main():
    conn = await asyncpg.connect(os.getenv('DATABASE_URL'))
    
    # Create merchants table if not exists
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS merchants (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            telegram_id BIGINT UNIQUE NOT NULL,
            business_name TEXT,
            phone TEXT,
            email TEXT,
            verified BOOLEAN DEFAULT FALSE,
            plan TEXT DEFAULT 'free',
            plan_expires TIMESTAMP,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    
    # Add columns if they don't exist (idempotent)
    await conn.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                          WHERE table_name='merchants' AND column_name='telegram_id') THEN
                ALTER TABLE merchants ADD COLUMN telegram_id BIGINT UNIQUE NOT NULL;
            END IF;
        END $$;
    ''')
    
    print("✅ Merchants table ready")
    await conn.close()

asyncio.run(main())
