import os
import json
import traceback
import httpx
import asyncio
from openai import AsyncOpenAI


# Open AI Client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))



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
mc_api = ManychatAPI()
#
#



async def validate_request_data(data):
    """Validates incoming request data."""
    required_fields = ["thread_id", "assistant_id", "bot_filter_tag", "manychat_id"]
    fields = {field: data.get(field) for field in required_fields}
    missing_fields = [field for field in required_fields if not fields[field] or fields[field] in ["", "null", None]]

    if missing_fields:
        await log("error", "Missing required fields", missing_fields=missing_fields, received_fields=data)
        return None

    return fields



async def advance_convo(convo_data):
    """Background task to handle conversation advancement."""
    try:
        thread_id = convo_data.get("thread_id")
        assistant_id = convo_data.get("assistant_id")
        bot_filter_tag = convo_data.get("bot_filter_tag")
        manychat_id = convo_data.get("manychat_id")

        # Run AI thread
        run_response = await openai_client.beta.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        if not run_response:
            raise Exception("Run failed")

        # Process the AI response
        await process_run_response(run_response, thread_id, bot_filter_tag, manychat_id)

    except Exception as e:
        await log("error", f"advance_convo -- Unexpected error --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)



async def process_run_response(run_response, thread_id, bot_filter_tag, manychat_id):
    """Process the AI thread response."""
    try:
        run_status = run_response.status

        if run_status == "completed":
            await process_message_response(run_response, thread_id, manychat_id)
        elif run_status == "requires_action":
            await process_function_response(run_response, thread_id, manychat_id)
        else:
            await log("error", f"Run thread failed --- {manychat_id}", response=run_response, manychat_id=manychat_id)

    except Exception as e:
        await log("error", f"process_run_response -- Unexpected error --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)



async def process_message_response(run_response, thread_id, manychat_id):
    """Process AI response messages."""
    try:
        run_id = run_response.id
        ai_messages = await openai_client.beta.threads.messages.list(thread_id=thread_id, run_id=run_id)
        ai_messages = ai_messages.data

        if not ai_messages:
            await log("error", f"No messages found in run response --- {manychat_id}", manychat_id=manychat_id)
            return None

        # Extract the content of the last message
        ai_content = ai_messages[-1].content[0].text.value
        if "【" in ai_content and "】" in ai_content:
            ai_content = ai_content[:ai_content.find("【")] + ai_content[ai_content.find("】") + 1:]

        # Send AI message to ManyChat
        await mc_api.send_message(manychat_id, ai_content)
        return None
    
    except Exception as e:
        await log("error", f"Error processing AI message response --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)



async def process_function_response(run_response, thread_id, manychat_id):
    """Process required action responses from AI."""
    try:
        run_id = run_response.id
        tool_call = run_response.required_action.submit_tool_outputs.tool_calls[0]
        function_args = json.loads(tool_call.function.arguments)

        # Submit tool outputs and wait for confirmation
        await openai_client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=[{"tool_call_id": tool_call.id, "output": "success"}]
        )

        # Wait for the function run to complete
        max_checks = 6
        for attempt in range(max_checks):
            await asyncio.sleep(5)  # Wait 5 seconds before checking status

            run_status = await openai_client.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run_id)

            await log("info", f"Function status check {attempt + 1} --- {manychat_id}", response=str(run_status), manychat_id=manychat_id)

            if run_status.status == "completed":
                break  # Exit loop once the function completes
        else:
            await log("error", f"Function did not complete after {max_checks} attempts --- {manychat_id}", manychat_id=manychat_id)
            return

        # Proceed only if tool output submission was successful
        if "scenario" in function_args:
            await change_assistant(function_args, thread_id, manychat_id)
        
        elif "endDemo" in function_args:
            await end_demo(function_args, thread_id, manychat_id)
            
        else:
            await log("error", f"Unknown function response --- {manychat_id}", function_args=function_args, manychat_id=manychat_id)

    except Exception as e:
        await log("error", f"Error processing function response --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)













# Actions
#
async def change_assistant(function_args, thread_id, manychat_id):
    try:
        assistant_map = {
            "Italian": os.getenv("Italian_ASST"),
            "ecommerce": os.getenv("ecommerce_ASST"),
            "GuidedWalkthrough": os.getenv("GuidedWalkthrough_ASST"),
            "ManualWalkthrough": os.getenv("ManualWalkthrough_ASST"),
            "HighTicket": os.getenv("HighTicket_ASST"),
            "Enagic": os.getenv("Enagic_ASST"),
            "mainMenu": os.getenv("mainMenu_ASST")
        }
        
        pathway = function_args["scenario"]
        assistant_id = assistant_map.get(pathway)
    
        if assistant_id:
            response = await mc_api.set_custom_field(
                manychat_id,
                "assistant_id",
                assistant_id
            )
            if response:
                await log("info", f"Switch to {assistant_id} -- {manychat_id}", manychat_id=manychat_id)
                
                # Run the thread again with the new assistant
                await advance_convo({
                    "thread_id": thread_id,
                    "assistant_id": assistant_id,
                    "bot_filter_tag": "demo filter",
                    "manychat_id": manychat_id
                })

    except Exception as e:
        await log("error", f"Error changing asst --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)






async def end_bot(function_args, thread_id, manychat_id):
    """End bot by updating ManyChat tags."""
    try:
        await mc_api.remove_tag(manychat_id, "demo filter")
        await mc_api.add_tag(manychat_id, "disable auto message")
    except Exception as e:
        await log("error", f"Error ending bot --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)



async def log(level, msg, **kwargs):
    """Centralized logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))
