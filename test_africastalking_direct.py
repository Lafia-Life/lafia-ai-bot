#!/usr/bin/env python3
"""
Direct test of Africa's Talking API without our application
"""

import requests

# Your current API details
API_KEY = "REDACTED_AFRICAS_TALKING_KEY"
USERNAME = "sandbox"

def test_authentication():
    """Test basic authentication"""
    print("Testing Authentication...")
    
    headers = {
        'ApiKey': API_KEY,
        'Accept': 'application/json'
    }
    
    # Test with both URLs
    urls = [
        "https://api.sandbox.africastalking.com/version1/user",
        "https://api.africastalking.com/version1/user"
    ]
    
    for url in urls:
        try:
            response = requests.get(f"{url}?username={USERNAME}", headers=headers, timeout=10)
            print(f"\n{url}:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error with {url}: {e}")

def test_sms_send():
    """Test SMS sending"""
    print("\n\nTesting SMS Sending...")
    
    headers = {
        'ApiKey': API_KEY,
        'Content-Type': 'application/x-www-form-urlencoded',
        'Accept': 'application/json'
    }
    
    data = {
        'username': USERNAME,
        'to': '+000000000',
        'message': 'Test from direct API call'
    }
    
    # Test with both URLs
    urls = [
        "https://api.sandbox.africastalking.com/version1/messaging",
        "https://api.africastalking.com/version1/messaging"
    ]
    
    for url in urls:
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            print(f"\n{url}:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
        except Exception as e:
            print(f"Error with {url}: {e}")

if __name__ == "__main__":
    print("=== Africa's Talking API Direct Test ===")
    print(f"API Key: {API_KEY[:20]}...")
    print(f"Username: {USERNAME}")
    
    test_authentication()
    test_sms_send()
    
    print("\n=== Test Complete ===")
    print("If all tests show 'authentication invalid', the issue is with:")
    print("1. API key needs activation in dashboard")
    print("2. Account needs phone/email verification") 
    print("3. SMS service needs to be enabled")
    print("4. Account needs credits (even in sandbox)")