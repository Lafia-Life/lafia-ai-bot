#!/usr/bin/env python3
"""
Test script for SMS integration
"""

import asyncio
import json
from app.services.sms_service import sms_service, send_sms_response
from app.schemas import ChatRequest
from app.services.retrieval import answer_question


async def test_sms_service():
    """Test basic SMS sending functionality"""
    print("Testing SMS Service...")
    
    # Test phone number formatting
    test_numbers = [
        "0701234567",
        "701234567", 
        "+000000000"
    ]
    
    for number in test_numbers:
        formatted = number
        if number.startswith('0'):
            formatted = '+256' + number[1:]
        elif not number.startswith('+'):
            formatted = '+256' + number
        print(f"  {number} → {formatted}")
    
    # Test message splitting
    long_message = "This is a very long message that should be split into multiple SMS parts because it exceeds the standard SMS length limit of 160 characters which is the maximum for a single SMS."
    
    chunks = sms_service._split_message(long_message, max_length=50)  # Smaller for demo
    print(f"\nMessage splitting test:")
    print(f"Original: {long_message}")
    print(f"Chunks ({len(chunks)}):")
    for i, chunk in enumerate(chunks, 1):
        print(f"  {i}: {chunk}")


async def test_ai_response():
    """Test AI question answering"""
    print("\nTesting AI Response...")
    
    try:
        # Test question
        request = ChatRequest(question="What is malaria?")
        response = answer_question(request)
        
        print(f"Question: {request.question}")
        print(f"Answer: {response.answer[:100]}...")
        print(f"Citations: {len(response.citations)}")
        
    except Exception as e:
        print(f"AI test failed: {e}")
        print("This is expected if no documents are uploaded or AI is not configured")


async def test_sms_response_formatting():
    """Test SMS response formatting"""
    print("\nTesting SMS Response Formatting...")
    
    question = "What are the symptoms of malaria?"
    answer = "Common malaria symptoms include fever, chills, headache, muscle aches, fatigue, nausea, and vomiting. Symptoms typically appear 10-15 days after an infected mosquito bite. Seek medical attention immediately if you experience these symptoms in malaria-endemic areas."
    
    # Format like the actual SMS response
    response_message = f"Q: {question[:50]}{'...' if len(question) > 50 else ''}\n\nA: {answer}"
    footer = "\n\n--\nMoH E-Learning Assistant\nSend questions anytime!"
    full_message = response_message + footer
    
    # Test splitting
    chunks = sms_service._split_message(full_message)
    
    print(f"Question: {question}")
    print(f"Answer: {answer}")
    print(f"Full SMS response ({len(chunks)} parts):")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n--- SMS Part {i} ---")
        print(chunk)


async def test_webhook_parsing():
    """Test webhook data parsing"""
    print("\nTesting Webhook Parsing...")
    
    # Simulate Africa's Talking webhook data
    webhook_data = {
        'to': '21000',
        'from': '+000000000',  # Note: Africa's Talking uses 'from' not 'from_'
        'text': 'What is malaria?',
        'date': '2023-10-24 12:00:00',
        'id': 'ATXid_sample123',
        'linkId': None
    }
    
    print(f"Webhook data: {json.dumps(webhook_data, indent=2)}")
    
    try:
        from app.services.sms_service import parse_incoming_sms
        sms = parse_incoming_sms(webhook_data)
        print(f"Parsed SMS:")
        print(f"  From: {sms.from_}")
        print(f"  To: {sms.to}")
        print(f"  Text: {sms.text}")
        print(f"  ID: {sms.id}")
    except Exception as e:
        print(f"Webhook parsing failed: {e}")


async def main():
    """Run all tests"""
    print("=== SMS Integration Test Suite ===\n")
    
    await test_sms_service()
    await test_ai_response()
    await test_sms_response_formatting()
    await test_webhook_parsing()
    
    print("\n=== Test Complete ===")
    print("\nTo test actual SMS sending:")
    print("1. Configure AFRICAS_TALKING_API_KEY in .env")
    print("2. Run: curl -X POST 'http://localhost:8000/api/sms/send' \\")
    print("     -H 'Content-Type: application/json' \\")
    print("     -d '{\"phone_number\": \"+000000000\", \"message\": \"Test from AI\"}'")


if __name__ == "__main__":
    asyncio.run(main())