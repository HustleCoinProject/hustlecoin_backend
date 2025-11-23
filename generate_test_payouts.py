#!/usr/bin/env python3
"""
Script to generate test payout requests for testing the bulk CSV functionality.
This script creates up to 30 pending payout requests with realistic test data.
"""

import asyncio
import random
from datetime import datetime, timedelta
from faker import Faker
import motor.motor_asyncio
from beanie import init_beanie
from data.models.models import User, Payout
from core.config import settings

# Initialize Faker for generating realistic test data
fake = Faker(['en_US', 'pt_PT'])  # English and Portuguese for Angola context

# Test data pools
ANGOLA_PHONE_PREFIXES = ['+244912', '+244913', '+244914', '+244915', '+244923', '+244924']
ANGOLA_BANKS = [
    'Banco BAI', 'Banco BIC', 'Banco Millennium Atlântico', 'Banco Sol',
    'Banco Económico', 'Banco de Fomento Angola', 'Banco Keve', 'Banco Yetu'
]

# Common Angolan names
ANGOLAN_FIRST_NAMES = [
    'João', 'Maria', 'António', 'Ana', 'Carlos', 'Isabel', 'Paulo', 'Catarina',
    'José', 'Teresa', 'Manuel', 'Rosa', 'Francisco', 'Fernanda', 'Pedro', 'Luísa',
    'Miguel', 'Cristina', 'Joaquim', 'Margarida', 'Daniel', 'Beatriz', 'Ricardo', 'Sofia',
    'Nuno', 'Carla', 'Rui', 'Paula', 'Sérgio', 'Mónica'
]

ANGOLAN_LAST_NAMES = [
    'Santos', 'Silva', 'Ferreira', 'Costa', 'Pereira', 'Oliveira', 'Rodrigues', 'Martins',
    'Sousa', 'Almeida', 'Ribeiro', 'Gonçalves', 'Pinto', 'Carvalho', 'Teixeira', 'Moreira',
    'Correia', 'Mendes', 'Nunes', 'Soares', 'Vieira', 'Monteiro', 'Cardoso', 'Cunha',
    'Melo', 'Barbosa', 'Castro', 'Coelho', 'Dias', 'Campos'
]


def generate_angola_phone():
    """Generate a realistic Angola phone number."""
    prefix = random.choice(ANGOLA_PHONE_PREFIXES)
    number = ''.join([str(random.randint(0, 9)) for _ in range(6)])
    return f"{prefix}{number}"


def generate_angola_iban():
    """Generate a realistic Angola IBAN."""
    # Angola IBAN format: AO06 BBBB CCCC CCCC CCCC CCCC C
    bank_code = ''.join([str(random.randint(0, 9)) for _ in range(4)])
    account = ''.join([str(random.randint(0, 9)) for _ in range(17)])
    return f"AO06{bank_code}{account}"


def generate_national_id():
    """Generate a realistic Angola national ID."""
    # Format: 9 digits + 2 letters
    digits = ''.join([str(random.randint(0, 9)) for _ in range(9)])
    letters = ''.join([chr(random.randint(65, 90)) for _ in range(2)])
    return f"{digits}{letters}"


def generate_angolan_name():
    """Generate a realistic Angolan name."""
    first = random.choice(ANGOLAN_FIRST_NAMES)
    last = random.choice(ANGOLAN_LAST_NAMES)
    return f"{first} {last}"


async def create_test_user(username: str, email: str) -> User:
    """Create a test user with sufficient HC balance."""
    user = User(
        username=username,
        email=email,
        hashed_password="$2b$12$dummy_hash_for_testing",  # Dummy hash
        hc_balance=random.randint(5000, 50000),  # Give users plenty of HC
        level=random.randint(1, 10),
        current_hustle=random.choice([
            "Street Vendor", "Taxi Driver", "Market Trader", "Mechanic", 
            "Hairdresser", "Restaurant Owner", "Shop Keeper", "Farmer"
        ])
    )
    
    # Add some payout info randomly
    if random.choice([True, False]):
        user.phone_number = generate_angola_phone()
        user.full_name = generate_angolan_name()
        user.national_id = generate_national_id()
    
    if random.choice([True, False]):
        user.bank_iban = generate_angola_iban()
        user.bank_name = random.choice(ANGOLA_BANKS)
    
    try:
        await user.create()
        print(f"✓ Created user: {username} ({email}) with {user.hc_balance} HC")
        return user
    except Exception as e:
        print(f"✗ Failed to create user {username}: {e}")
        return None


async def create_test_payout(user: User, payout_number: int) -> Payout:
    """Create a test payout request."""
    
    # Random payout amount (respecting minimum)
    min_amount = getattr(settings, 'MINIMUM_PAYOUT_HC', 500)
    amount_hc = random.randint(min_amount, min(user.hc_balance, 5000))
    
    # Choose payout method
    payout_method = random.choice(['multicaixa_express', 'bank_transfer'])
    
    # Calculate Kwanza amount
    conversion_rate = getattr(settings, 'PAYOUT_CONVERSION_RATE', 10.0)
    amount_kwanza = round(amount_hc / conversion_rate, 2)
    
    # Create payout with realistic data
    payout_data = {
        'user_id': user.id,
        'amount_hc': amount_hc,
        'amount_kwanza': amount_kwanza,
        'conversion_rate': conversion_rate,
        'payout_method': payout_method,
        'status': 'pending'
    }
    
    if payout_method == 'multicaixa_express':
        payout_data.update({
            'phone_number': user.phone_number or generate_angola_phone(),
            'full_name': user.full_name or generate_angolan_name(),
            'national_id': user.national_id or generate_national_id()
        })
    else:  # bank_transfer
        payout_data.update({
            'bank_iban': user.bank_iban or generate_angola_iban(),
            'bank_name': user.bank_name or random.choice(ANGOLA_BANKS),
            'full_name': user.full_name or generate_angolan_name()
        })
    
    # Vary creation times to simulate real requests over time
    hours_ago = random.randint(1, 72)  # 1 to 72 hours ago
    created_at = datetime.utcnow() - timedelta(hours=hours_ago)
    payout_data['created_at'] = created_at
    
    try:
        payout = Payout(**payout_data)
        await payout.create()
        
        # Deduct HC from user balance (simulate the payout request process)
        await user.update({"$inc": {"hc_balance": -amount_hc}})
        
        method_display = "Multicaixa" if payout_method == 'multicaixa_express' else "Bank Transfer"
        print(f"✓ Created payout #{payout_number}: {amount_hc} HC ({amount_kwanza} AOA) - {method_display}")
        return payout
        
    except Exception as e:
        print(f"✗ Failed to create payout #{payout_number}: {e}")
        return None


async def main():
    """Main function to generate test data."""
    print("=== HustleCoin Test Payout Generator ===\n")
    
    try:
        # Initialize database connection
        print("Connecting to database...")
        client = motor.motor_asyncio.AsyncIOMotorClient(settings.MONGO_DETAILS)
        await init_beanie(
            database=client.get_database("hustlecoin_db"), 
            document_models=[User, Payout]
        )
        print("✓ Database connected successfully\n")
        
        # Ask for number of payouts to create
        try:
            num_payouts = int(input("How many test payouts do you want to create? (1-30): ") or "10")
            num_payouts = max(1, min(30, num_payouts))  # Clamp between 1 and 30
        except ValueError:
            num_payouts = 10
            print(f"Invalid input, using default: {num_payouts} payouts")
        
        print(f"\nGenerating {num_payouts} test payout requests...\n")
        
        created_payouts = 0
        created_users = 0
        
        for i in range(1, num_payouts + 1):
            try:
                # Create or use existing user
                username = f"test_user_{i:03d}"
                email = f"test{i:03d}@example.com"
                
                # Check if user exists
                existing_user = await User.find_one({"username": username})
                
                if existing_user:
                    user = existing_user
                    print(f"✓ Using existing user: {username}")
                else:
                    user = await create_test_user(username, email)
                    if user:
                        created_users += 1
                
                if user and user.hc_balance >= getattr(settings, 'MINIMUM_PAYOUT_HC', 500):
                    payout = await create_test_payout(user, i)
                    if payout:
                        created_payouts += 1
                else:
                    print(f"✗ User {username} doesn't have enough HC balance")
                    
            except Exception as e:
                print(f"✗ Error creating payout #{i}: {e}")
                continue
        
        print(f"\n=== Summary ===")
        print(f"✓ Created {created_users} new users")
        print(f"✓ Created {created_payouts} payout requests")
        print(f"✓ All payouts are in 'pending' status")
        
        # Show some statistics
        if created_payouts > 0:
            total_pending = await Payout.find({"status": "pending"}).count()
            print(f"✓ Total pending payouts in database: {total_pending}")
            
            # Show breakdown by method
            multicaixa_count = await Payout.find({
                "status": "pending", 
                "payout_method": "multicaixa_express"
            }).count()
            bank_count = await Payout.find({
                "status": "pending", 
                "payout_method": "bank_transfer"
            }).count()
            
            print(f"  - Multicaixa Express: {multicaixa_count}")
            print(f"  - Bank Transfer: {bank_count}")
        
        print(f"\n🎉 Test data generation complete!")
        print(f"You can now test the bulk CSV functionality in the admin panel.")
        print(f"Go to: http://localhost:8000/admin/payouts/management")
        
    except Exception as e:
        print(f"✗ Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)