# SMS Integration for Rural Uganda

This document explains how to set up SMS-based AI assistance for users in rural Uganda using Africa's Talking SMS gateway.

## Overview

The SMS integration allows users without internet access to:
- Send questions via SMS to a shortcode or phone number
- Receive AI-generated answers based on your knowledge base
- Access the same AI capabilities as the web interface

## Why Africa's Talking?

Africa's Talking is the recommended SMS provider for Uganda because:
- **Local presence**: Based in Kenya with strong East Africa coverage
- **Uganda operators**: Direct integration with MTN, Airtel, Africell
- **Affordable**: Competitive rates for local SMS traffic
- **Reliable**: Designed for African telecommunications infrastructure
- **Simple setup**: Easy API integration

## Setup Instructions

### 1. Create Africa's Talking Account

1. Go to [africastalking.com](https://africastalking.com)
2. Sign up for an account
3. Complete verification process
4. Purchase SMS credits (rates vary by volume)

### 2. Get API Credentials

1. Login to your Africa's Talking dashboard
2. Go to "Apps" → "Sandbox" (for testing) or create a new app
3. Note your **API Key** and **Username**
4. For production, you'll also get a **Shortcode** or **Sender ID**

### 3. Configure Environment Variables

Add these to your `.env` file:

```bash
# SMS Configuration
AFRICAS_TALKING_API_KEY=your_api_key_here
AFRICAS_TALKING_USERNAME=your_username_here  
SMS_WEBHOOK_SECRET=optional_webhook_secret
```

### 4. Set Up Webhook

1. In Africa's Talking dashboard, go to SMS → Callback URLs
2. Set your webhook URL: `https://yourdomain.com/api/sms/webhook`
3. Choose POST method
4. Save configuration

### 5. Test the Integration

```bash
# Test sending SMS manually
curl -X POST "http://localhost:8000/api/sms/send" \
  -H "Content-Type: application/json" \
  -d '{
    "phone_number": "+000000000",
    "message": "Test message from AI assistant"
  }'
```

## How It Works

### SMS Flow

1. **User sends SMS**: User texts question to your shortcode/number
2. **Webhook triggered**: Africa's Talking sends webhook to your server
3. **AI processing**: Your FastAPI app processes question using existing AI logic
4. **Response sent**: AI answer is sent back via SMS

### Message Handling

- **Long messages**: Automatically split into multiple SMS (160 char limit)
- **Context preservation**: Original question included in response for clarity  
- **Error handling**: Graceful fallbacks for processing errors

### Example Interaction

```
User SMS: "What are the symptoms of malaria?"

AI Response SMS: "(1/2) Q: What are the symptoms of malaria?

A: Common malaria symptoms include fever, chills, headache, muscle aches, fatigue, nausea, and vomiting. Symptoms typically appear 10-15 days after..."

Second SMS: "(2/2) ...infected mosquito bite. Seek medical attention immediately if you experience these symptoms in malaria-endemic areas.

--
MoH E-Learning Assistant
Send questions anytime!"
```

## Uganda Phone Number Formats

The system automatically handles Uganda phone number formats:

- `0701234567` → `+000000000`
- `701234567` → `+000000000`
- `+000000000` → `+000000000` (no change)

## Costs and Considerations

### SMS Costs (Approximate)
- **Local SMS in Uganda**: ~$0.01-0.03 USD per SMS
- **Volume discounts**: Available for large deployments
- **Credits**: Purchase in advance, no monthly fees

### Technical Requirements
- **Internet**: Your server needs internet (users don't)
- **Uptime**: Critical for real-time SMS responses
- **Storage**: Same as web version for knowledge base

### Scaling Considerations
- **Response time**: SMS responses typically within 5-30 seconds
- **Throughput**: Handle hundreds of concurrent SMS requests
- **Reliability**: Built-in retry mechanisms for failed messages

## Production Deployment

### SSL Certificate Required
Africa's Talking requires HTTPS webhooks in production:

```bash
# Use Let's Encrypt for free SSL
sudo certbot --nginx -d yourdomain.com
```

### Load Balancing
For high volume, consider:
- Multiple FastAPI instances
- Redis for caching responses
- Queue system for SMS processing

### Monitoring
Track these metrics:
- SMS success/failure rates
- Response times
- API usage and costs
- User engagement patterns

## Alternative SMS Providers

If Africa's Talking isn't suitable, alternatives include:

### Twilio
- **Global coverage** including Uganda
- **Higher costs** but very reliable
- **Excellent documentation** and support tools

```python
# Twilio configuration (alternative)
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_PHONE_NUMBER=your_twilio_number
```

### Direct Operator Integration
- **MTN Uganda**, **Airtel Uganda** direct APIs
- **Lower costs** for very high volume
- **More complex** setup and certification process

### Local SMS Aggregators
- **Yo! Uganda**, **SMS Solutions Uganda**
- **Local support** and relationships
- **Competitive pricing** for domestic traffic

## Troubleshooting

### Common Issues

1. **Webhook not receiving SMS**
   - Check callback URL configuration
   - Verify HTTPS certificate
   - Test webhook endpoint directly

2. **SMS not sending**
   - Check API credentials
   - Verify sufficient credits
   - Review phone number formatting

3. **Long response times**
   - Optimize AI model inference
   - Implement response caching
   - Use async processing

### Testing Commands

```bash
# Test webhook endpoint
curl -X POST "https://yourdomain.com/api/sms/webhook" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "to=21000&from=%2B+000000000&text=test%20question&date=2023-10-24+12%3A00%3A00&id=test123"

# Check API status
curl "https://api.africastalking.com/version1/user?username=sandbox" \
  -H "ApiKey: your_api_key"
```

## Security Considerations

- **Webhook verification**: Validate incoming webhooks
- **Rate limiting**: Prevent SMS spam/abuse
- **Content filtering**: Sanitize user inputs
- **Data privacy**: Handle phone numbers securely

## Support and Resources

- **Africa's Talking Docs**: [docs.africastalking.com](https://docs.africastalking.com)
- **SMS Rates**: Contact Africa's Talking sales for volume pricing
- **Technical Support**: Available through their developer portal

This SMS integration makes your AI assistant accessible to millions of Ugandans who rely on basic mobile phones and SMS for communication, extending the reach of educational and health information to rural communities.