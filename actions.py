import os
import httpx
import json
import traceback


### Manychat class

class ManychatAPI:
    BASE_URL = "https://api.manychat.com/fb"
    
    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("MANYCHAT_API_KEY")
        
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
    
    async def add_tag(self, subscriber_id, tag_name):
        return await self._request("POST", "/tag/addTagByName", data={
            "subscriber_id": subscriber_id,
            "tag_name": tag_name
        }, function_name="add_tag", subscriber_id=subscriber_id)
    
    async def remove_tag(self, subscriber_id, tag_name):
        return await self._request("POST", "/tag/removeTagByName", data={
            "subscriber_id": subscriber_id,
            "tag_name": tag_name
        }, function_name="remove_tag", subscriber_id=subscriber_id)
    
    async def set_custom_field(self, subscriber_id, field_name, field_value):
        return await self._request("POST", "/custom_field/setCustomFieldByName", data={
            "subscriber_id": subscriber_id,
            "field_name": field_name,
            "field_value": field_value
        }, function_name="set_custom_field", subscriber_id=subscriber_id)








### Action functions

mc_api = ManychatAPI()

async def end_bot(function_args, thread_id, manychat_id):
    """End bot by updating ManyChat tags."""
    try:
        await mc_api.remove_tag(manychat_id, "auto message active")
        await mc_api.add_tag(manychat_id, "disable auto message")
    except Exception as e:
        await log("error", f"Error ending bot --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)


async def change_assistant(function_args, thread_id, manychat_id):
    pathway = function_args["scenario"]
    if pathway == "Italian":
        mc_api.set_custom_field(
            manychat_id,
            "assistant_id",
            os.getenv("Italian_ASST")
        )
    elif pathway == "ecommerce":
        mc_api.set_custom_field(
            manychat_id,
            "assistant_id",
            os.getenv("ecommerce_ASST")
        )
    elif pathway == "mainMenu":
        mc_api.set_custom_field(
            manychat_id,
            "assistant_id",
            os.getenv("mainMenu_ASST")
        )






