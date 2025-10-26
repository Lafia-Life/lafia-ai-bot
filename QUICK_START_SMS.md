# Africa's Talking SMS Setup - Quick Start Guide

## ✅ Configuration Complete!

Your SMS integration is properly configured with:
- **Username**: swiftload
- **API Key**: atsk_...d415a402 ✅

## 🧪 Testing Your Setup

### Sandbox Environment Limitations

Since you're using the sandbox environment, there are some restrictions:

1. **Test Phone Numbers Only**: In sandbox, you can only send to specific test numbers
2. **Limited Recipients**: Real phone numbers won't receive SMS in sandbox mode

### Valid Test Numbers for Sandbox

Try these Africa's Talking test numbers:
- `+254711XXXYYY` (Kenya test numbers)
- `+256714XXXYYY` (Uganda test numbers)

### Moving to Production

To send to real Uganda phone numbers:

1. **Upgrade to Production**:
   - Go to your Africa's Talking dashboard
   - Navigate to "Apps" → Create a production app
   - Complete business verification process

2. **Add Credits**:
   - Purchase SMS credits in your dashboard
   - Minimum top-up varies by country

3. **Update Environment**:
   ```bash
   AFRICAS_TALKING_USERNAME=your_production_app_name
   AFRICAS_TALKING_API_KEY=your_production_api_key
   ```

## 🚀 Testing Steps

### 1. Test with Valid Test Number

Use the SMS Admin interface at: http://localhost:8000/sms-admin

Try sending to a test number like: `+000000000`

### 2. Test the Complete AI Flow

1. Upload some documents to your knowledge base first
2. Use the "Test AI + SMS Flow" in the admin interface
3. Ask a question like: "What is malaria?"

### 3. Set Up Webhook (for receiving SMS)

1. In your Africa's Talking dashboard:
   - Go to SMS → Callback URLs
   - Set: `https://yourdomain.com/api/sms/webhook`
   - Method: POST

2. For local testing, use ngrok:
   ```bash
   ngrok http 8000
   # Use the https URL for webhook
   ```

## 🛠️ Troubleshooting

### SMS Sending Fails
- ✅ Check credit balance in dashboard
- ✅ Verify phone number format (+256...)
- ✅ Use test numbers in sandbox
- ✅ Check API key permissions

### Webhook Not Working
- ✅ Ensure HTTPS for production webhook
- ✅ Use ngrok for local testing
- ✅ Check firewall/port access

### AI Responses Empty
- ✅ Upload documents first
- ✅ Configure OpenAI/DeepSeek API key
- ✅ Check if documents are indexed

## 📱 Next Steps

1. **Test in Admin Interface**: Visit http://localhost:8000/sms-admin
2. **Upload Health Documents**: Add PDFs to your knowledge base
3. **Configure Production**: When ready for real users
4. **Set Up Webhook**: For two-way SMS communication

## 💡 Production Considerations

### Costs (Uganda)
- **SMS Rate**: ~$0.01-0.03 per SMS
- **Typical AI Response**: 1-3 SMS parts
- **Daily Volume**: 100 questions = ~$2-6/day

### Scale Planning
- **High Volume**: Consider dedicated shortcode
- **Load Balancing**: Multiple server instances
- **Monitoring**: Track success rates and costs

Your SMS integration is ready! Start with the admin interface to test, then move to production when you're satisfied with the functionality.
