import os
import json
import traceback
import httpx
import asyncio
from utils import log  # Updated import

class ManychatAPI:
    BASE_URL = "https://api.manychat.com/fb"
    
    def __init__(self, api_key):
        if not api_key:
            raise ValueError("ManyChat API key is required")
        self.api_key = api_key
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    async def _request(self, method, endpoint, params=None, data=None, function_name="unknown", subscriber_id=None):
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=self.headers, params=params, json=data)
                
                if not response.is_success:
                    await log("error", f"Manychat API --- {function_name} Failed --- {subscriber_id}",
                              subscriber_id=subscriber_id, status_code=response.status_code, response=response.text)
                    return None
                
                response_data = response.json()
                if method == "POST" and response_data.get("status") != "success":
                    await log("error", f"Manychat API --- {function_name} Failed --- {subscriber_id}",
                              subscriber_id=subscriber_id, response=response_data)
                    return None
                
                return response_data
        except Exception as e:
            await log("error", f"Manychat API --- {function_name} Failed --- {subscriber_id}",
                      subscriber_id=subscriber_id, error=str(e), traceback=traceback.format_exc())
            return None
    
    async def send_message(self, subscriber_id, message):
        return await self._request("POST", "/sending/sendContent", data={
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "type": "instagram",
                    "messages": [
                        {"type": "text", "text": message}
                    ]
                }
            },
            "message_tag": "ACCOUNT_UPDATE"
        }, function_name="send_message", subscriber_id=subscriber_id)
    
    async def send_audio(self, subscriber_id, audio_url):
        return await self._request("POST", "/sending/sendContent", data={
            "subscriber_id": subscriber_id,
            "data": {
                "version": "v2",
                "content": {
                    "type": "instagram",
                    "messages": [
                        {"type": "audio", "url": audio_url}
                    ]
                }
            },
            "message_tag": "ACCOUNT_UPDATE"
        }, function_name="send_audio", subscriber_id=subscriber_id)
    
    async def add_tag(self, subscriber_id, tag_name):
        return await self._request("POST", "/subscriber/addTagByName", data={
            "subscriber_id": subscriber_id,
            "tag_name": tag_name
        }, function_name="add_tag", subscriber_id=subscriber_id)
    
    async def remove_tag(self, subscriber_id, tag_name):
        return await self._request("POST", "/subscriber/removeTagByName", data={
            "subscriber_id": subscriber_id,
            "tag_name": tag_name
        }, function_name="remove_tag", subscriber_id=subscriber_id)
    
    async def set_custom_field(self, subscriber_id, field_name, field_value):
        return await self._request("POST", "/subscriber/setCustomFieldByName", data={
            "subscriber_id": subscriber_id,
            "field_name": field_name,
            "field_value": field_value
        }, function_name="set_custom_field", subscriber_id=subscriber_id)



#
# Initialize manychat api
#mc_api = ManychatAPI(api_key=os.getenv("MANYCHAT_API_KEY"))
#
#