"""
Test script for API key management endpoints.

Demonstrates:
1. Create new API key
2. List all API keys
3. Use new API key to make API calls
4. Revoke an API key
"""

import requests
import json

# API configuration
API_BASE = "http://localhost:8000/v1"
INITIAL_API_KEY = "demo_api_key_12345678901234567890"  # Demo customer's original API key

HEADERS = {
    "X-API-Key": INITIAL_API_KEY,
    "Content-Type": "application/json"
}


def test_create_api_key():
    """Test 1: Create a new API key."""
    print("=" * 80)
    print("TEST 1: Create New API Key")
    print("=" * 80)

    payload = {
        "name": "Production Server",
        "description": "API key for production deployment",
        "expires_days": 90
    }

    print(f"\n📤 POST {API_BASE}/account/api-keys")
    print(f"   Name: {payload['name']}")
    print(f"   Expires: {payload['expires_days']} days")

    response = requests.post(
        f"{API_BASE}/account/api-keys",
        headers=HEADERS,
        json=payload
    )

    if response.status_code == 200:
        data = response.json()['data']
        print(f"\n✅ API Key Created Successfully")
        print(f"   Key ID: {data['key_id']}")
        print(f"   Name: {data['name']}")
        print(f"   API Key: {data['api_key'][:20]}...")
        print(f"   Created: {data['created_at']}")
        print(f"   Expires: {data['expires_at']}")
        print(f"\n   ⚠️  {data['warning']}")

        return data['key_id'], data['api_key']
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return None, None


def test_list_api_keys():
    """Test 2: List all API keys."""
    print("\n" + "=" * 80)
    print("TEST 2: List All API Keys")
    print("=" * 80)

    print(f"\n📋 GET {API_BASE}/account/api-keys")

    response = requests.get(
        f"{API_BASE}/account/api-keys",
        headers=HEADERS
    )

    if response.status_code == 200:
        data = response.json()['data']
        print(f"\n✅ Found {data['total']} total keys ({data['active']} active)")

        for key in data['keys']:
            status = "🔴 REVOKED" if key['revoked'] else "🟢 ACTIVE"
            print(f"\n   {status} {key['name']}")
            print(f"      Key ID: {key['key_id']}")
            print(f"      Prefix: {key['key_prefix']}...")
            print(f"      Created: {key['created_at']}")
            if key['expires_at']:
                print(f"      Expires: {key['expires_at']}")
            if key['last_used_at']:
                print(f"      Last Used: {key['last_used_at']}")
            if key['revoked']:
                print(f"      Revoked: {key['revoked_at']}")
                if key['revoked_reason']:
                    print(f"      Reason: {key['revoked_reason']}")

        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_use_new_api_key(new_api_key):
    """Test 3: Use new API key to make a request."""
    print("\n" + "=" * 80)
    print("TEST 3: Use New API Key")
    print("=" * 80)

    print(f"\n🔑 Testing new API key: {new_api_key[:20]}...")

    new_headers = {
        "X-API-Key": new_api_key,
        "Content-Type": "application/json"
    }

    # Try to list API keys with the new key
    response = requests.get(
        f"{API_BASE}/account/api-keys",
        headers=new_headers
    )

    if response.status_code == 200:
        print(f"\n✅ New API Key Works!")
        print(f"   Successfully authenticated with new key")
        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_revoke_api_key(key_id):
    """Test 4: Revoke an API key."""
    print("\n" + "=" * 80)
    print("TEST 4: Revoke API Key")
    print("=" * 80)

    payload = {
        "reason": "Testing revocation functionality"
    }

    print(f"\n🗑️  DELETE {API_BASE}/account/api-keys/{key_id}")

    response = requests.delete(
        f"{API_BASE}/account/api-keys/{key_id}",
        headers=HEADERS,
        json=payload
    )

    if response.status_code == 200:
        data = response.json()['data']
        print(f"\n✅ API Key Revoked")
        print(f"   Key ID: {data['key_id']}")
        print(f"   Revoked At: {data['revoked_at']}")
        print(f"   Message: {data['message']}")
        return True
    else:
        print(f"\n❌ Failed: {response.status_code}")
        print(f"   Error: {response.text}")
        return False


def test_revoked_key_fails(revoked_api_key):
    """Test 5: Verify revoked key no longer works."""
    print("\n" + "=" * 80)
    print("TEST 5: Verify Revoked Key Cannot Be Used")
    print("=" * 80)

    revoked_headers = {
        "X-API-Key": revoked_api_key,
        "Content-Type": "application/json"
    }

    print(f"\n🔒 Attempting to use revoked key: {revoked_api_key[:20]}...")

    response = requests.get(
        f"{API_BASE}/account/api-keys",
        headers=revoked_headers
    )

    if response.status_code == 401:
        print(f"\n✅ Revocation Works Correctly")
        print(f"   Revoked key was rejected (401 Unauthorized)")
        return True
    else:
        print(f"\n❌ Security Issue: Revoked key still works!")
        print(f"   Status: {response.status_code}")
        return False


def main():
    """Run complete API key management test workflow."""
    print("\n🔐 API Key Management Test Suite")
    print("Testing API key creation, listing, usage, and revocation\n")

    try:
        # Test 1: Create new API key
        new_key_id, new_api_key = test_create_api_key()
        if not new_key_id:
            print("\n❌ Test suite failed at CREATE")
            return

        # Test 2: List all API keys
        if not test_list_api_keys():
            print("\n❌ Test suite failed at LIST")
            return

        # Test 3: Use new API key
        if not test_use_new_api_key(new_api_key):
            print("\n❌ Test suite failed at USE NEW KEY")
            return

        # Test 4: Revoke the new API key
        if not test_revoke_api_key(new_key_id):
            print("\n❌ Test suite failed at REVOKE")
            return

        # Test 5: Verify revoked key doesn't work
        if not test_revoked_key_fails(new_api_key):
            print("\n❌ Test suite failed at REVOKED KEY VALIDATION")
            return

        print("\n" + "=" * 80)
        print("✅ ALL TESTS PASSED!")
        print("=" * 80)

        print("\n📚 API Key Management Endpoints:")
        print(f"   POST   {API_BASE}/account/api-keys (create)")
        print(f"   GET    {API_BASE}/account/api-keys (list)")
        print(f"   DELETE {API_BASE}/account/api-keys/{{key_id}} (revoke)")

        print("\n💡 Best Practices:")
        print("   • Use separate API keys for different environments (prod, staging, dev)")
        print("   • Set expiration dates for temporary keys")
        print("   • Rotate keys periodically")
        print("   • Revoke keys immediately if compromised")
        print("   • Never commit API keys to version control")

    except Exception as e:
        print(f"\n❌ Test suite error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    main()
