# 🔧 SMS Troubleshooting Guide

## Current Status: Authentication Invalid (401)

Your SMS integration is properly coded but the Africa's Talking API is returning "authentication invalid". Here's how to fix this:

## ✅ Step 1: Verify API Key in Dashboard

1. **Log into Africa's Talking Sandbox**: https://account.africastalking.com
2. **Go to Apps → Sandbox**
3. **Navigate to API section**
4. **Copy the EXACT API key** (it should start with `atsk_`)
5. **Verify the key is 64+ characters long**

## ✅ Step 2: Check API Key Activation

Some API keys need activation:

1. **In your dashboard, look for "API Status"**
2. **Check if there's an "Activate API" button**
3. **Some accounts require phone verification first**
4. **Ensure SMS service is enabled for your app**

## ✅ Step 3: Verify Username

- **Sandbox username should be exactly**: `sandbox`
- **NOT** `swiftload` or any other name
- **Case sensitive**

## ✅ Step 4: Update Configuration

If you get a new/different API key, update `.env`:

```bash
AFRICAS_TALKING_API_KEY=your_new_api_key_here
AFRICAS_TALKING_USERNAME=sandbox
```

Then restart the server:
```bash
pkill -f uvicorn
# Start again with your task runner
```

## ✅ Step 5: Test Authentication

Use this command to test just the authentication:

```bash
curl -H "ApiKey: YOUR_API_KEY" \
  "https://api.sandbox.africastalking.com/version1/user?username=sandbox"
```

**Expected response**: Should show your account details, NOT "authentication invalid"

## ✅ Step 6: Alternative Testing

If sandbox continues to fail, try:

1. **Create a production app** (even for testing)
2. **Add some credits** ($1-2 minimum)
3. **Use production API key and app name**

## 🎯 Quick Debug Commands

Once you have the correct API key:

```bash
# Test basic auth
curl -H "ApiKey: YOUR_KEY" \
  "https://api.sandbox.africastalking.com/version1/user?username=sandbox"

# Test SMS via our debug endpoint
curl -X POST "http://localhost:8000/api/sms/debug" \
  -H "Content-Type: application/json" \
  -d '{"phone_number": "+000000000", "message": "Hello Uganda!"}'

# Test via admin interface
# Visit: http://localhost:8000/sms-admin
```

## 🔍 Common Issues

### "Authentication Invalid"
- ✅ Double-check API key copy/paste
- ✅ Look for extra spaces or characters
- ✅ Verify sandbox vs production key
- ✅ Check if API needs activation

### "Insufficient Credits"
- ✅ Add credits in dashboard
- ✅ Minimum $1-2 for testing
- ✅ Check billing section

### "Invalid Phone Number"
- ✅ Use format: +000000000
- ✅ Uganda numbers: +256...
- ✅ No spaces or special characters

## 📞 Next Steps

1. **Check your dashboard** for API activation
2. **Verify exact API key** (copy fresh from dashboard)
3. **Update .env file** if needed
4. **Test authentication** with curl command above
5. **Try SMS sending** once auth works

## 🎉 When It Works

You'll see:
- ✅ Authentication endpoint returns account details
- ✅ SMS debug endpoint shows success status
- ✅ Your phone receives test messages
- ✅ Admin interface shows green status

The integration code is ready - we just need the correct API credentials!

---

**Current Error**: API Key authentication failing
**Next Action**: Verify API key in Africa's Talking dashboard
**Test Phone**: +000000000