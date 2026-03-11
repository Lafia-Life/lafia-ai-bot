import logging
import json
from typing import Optional
import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import get_settings

logger = logging.getLogger(__name__)


class SMSMessage(BaseModel):
    phone_number: str
    message: str
    
    
class IncomingSMS(BaseModel):
    """Model for incoming SMS from Africa's Talking webhook"""
    to: str  # Your shortcode/number
    from_: str = Field(alias="from")  # Sender's phone number
    text: str
    date: str
    id: str
    linkId: Optional[str] = None

    model_config = ConfigDict(populate_by_name=True)


class SMSService:
    """SMS service using Africa's Talking API for Uganda"""
    
    def __init__(self):
        self.settings = get_settings()
        self.api_key = getattr(self.settings, 'africas_talking_api_key', None)
        self.username = getattr(self.settings, 'africas_talking_username', 'sandbox')
        # Use sandbox URL for sandbox username
        if self.username == 'sandbox':
            self.base_url = "https://api.sandbox.africastalking.com/version1"
        else:
            self.base_url = "https://api.africastalking.com/version1"
        
        if not self.api_key:
            logger.warning("Africa's Talking API key not configured")
    
    async def send_sms(self, phone_number: str, message: str) -> bool:
        """
        Send SMS via Africa's Talking API
        
        Args:
            phone_number: Phone number in format +256XXXXXXXXX (Uganda)
            message: Text message (max 160 chars for single SMS)
        
        Returns:
            bool: True if successful
        """
        if not self.api_key:
            logger.error("SMS service not configured - missing API key")
            return False
            
        # Format phone number for Uganda if needed
        if phone_number.startswith('0'):
            phone_number = '+256' + phone_number[1:]
        elif not phone_number.startswith('+'):
            phone_number = '+256' + phone_number
            
        headers = {
            'apiKey': self.api_key,
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json'
        }
        
        # Split long messages into chunks (SMS limit ~160 chars)
        message_chunks = self._split_message(message)
        
        success = True
        for chunk in message_chunks:
            data = {
                'username': self.username,
                'to': phone_number,
                'message': chunk
            }
            
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        f"{self.base_url}/messaging",
                        headers=headers,
                        data=data,
                        timeout=30.0
                    )
                    
                    logger.info(f"SMS API Response: {response.status_code} - {response.text}")
                    
                    if response.status_code == 201:
                        result = response.json()
                        sms_recipients = result.get('SMSMessageData', {}).get('Recipients', [])
                        if sms_recipients and sms_recipients[0].get('status') == 'Success':
                            logger.info(f"SMS sent successfully to {phone_number}")
                        else:
                            logger.error(f"SMS failed: {result}")
                            success = False
                    else:
                        logger.error(f"SMS API error: {response.status_code} - {response.text}")
                        success = False
                        
            except Exception as e:
                logger.error(f"SMS sending failed: {str(e)}")
                success = False
                
        return success
    
    def _split_message(self, message: str, max_length: int = 155) -> list[str]:
        """Split long messages into SMS-sized chunks"""
        if len(message) <= max_length:
            return [message]
            
        chunks = []
        words = message.split()
        current_chunk = ""
        
        for word in words:
            test_chunk = current_chunk + (" " if current_chunk else "") + word
            if len(test_chunk) <= max_length:
                current_chunk = test_chunk
            else:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = word
                
        if current_chunk:
            chunks.append(current_chunk)
            
        # Add part indicators for multi-part messages
        if len(chunks) > 1:
            for i, chunk in enumerate(chunks):
                chunks[i] = f"({i+1}/{len(chunks)}) {chunk}"
                
        return chunks


# Global SMS service instance
sms_service = SMSService()


async def send_sms_response(phone_number: str, question: str, answer: str) -> bool:
    """
    Send AI response via SMS with context
    
    Args:
        phone_number: Recipient phone number
        question: Original question (for context)
        answer: AI generated answer
    """
    # Format response message
    response_message = f"Q: {question[:50]}{'...' if len(question) > 50 else ''}\n\nA: {answer}"
    
    # Add helpful footer for rural users
    footer = "\n\n--\nMoH E-Learning Assistant\nSend questions anytime!"
    
    full_message = response_message + footer
    
    return await sms_service.send_sms(phone_number, full_message)


def parse_incoming_sms(webhook_data: dict) -> IncomingSMS:
    """Parse incoming SMS webhook from Africa's Talking"""
    return IncomingSMS(**webhook_data)
