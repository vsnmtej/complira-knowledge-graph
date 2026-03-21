"""
Create demo customer profile for testing VEX API.
"""

import bcrypt
from complira_graph.db import get_db

# Demo API key (32+ characters as required)
DEMO_API_KEY = "demo_api_key_12345678901234567890"
DEMO_CUSTOMER_ID = "demo_customer"

def create_demo_customer():
    """Create demo customer profile in database."""
    db = get_db()

    # Hash the API key
    salt = bcrypt.gensalt(rounds=12)
    api_key_hash = bcrypt.hashpw(DEMO_API_KEY.encode(), salt).decode()

    # Create customer profile
    customer_profile = {
        "_key": DEMO_CUSTOMER_ID,
        "id": DEMO_CUSTOMER_ID,
        "name": "Demo Customer",
        "email": "demo@example.com",
        "api_key_hash": api_key_hash,
        "tier": "enterprise",
        "enabled": True,
        "created_at": "2026-03-10T00:00:00Z",
        "database_name": f"customer_{DEMO_CUSTOMER_ID}",
    }

    # Check if customer_profiles collection exists
    if not db.has_collection("customer_profiles"):
        print("Creating customer_profiles collection...")
        db.create_collection("customer_profiles", edge=False)

    collection = db.collection("customer_profiles")

    # Check if demo customer already exists
    if collection.has(DEMO_CUSTOMER_ID):
        print(f"✅ Demo customer already exists: {DEMO_CUSTOMER_ID}")
        print(f"   API Key: {DEMO_API_KEY}")
    else:
        # Insert customer profile
        collection.insert(customer_profile)
        print(f"✅ Demo customer created successfully!")
        print(f"   Customer ID: {DEMO_CUSTOMER_ID}")
        print(f"   API Key: {DEMO_API_KEY}")

    print(f"\n📝 Update your test script with:")
    print(f'   API_KEY = "{DEMO_API_KEY}"')


if __name__ == '__main__':
    create_demo_customer()
