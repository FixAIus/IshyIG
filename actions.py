import os
import json
import traceback
import httpx
from openai import AsyncOpenAI


# Open AI Client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))



class ManychatAPI:
    """Handles ManyChat API requests."""
    BASE_URL = "https://api.manychat.com/fb"

    def __init__(self, api_key=None):
        self.api_key = api_key or os.getenv("MANYCHAT_API_KEY")
        self.headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def _request(self, method, endpoint, data=None, function_name="unknown", subscriber_id=None):
        """Handles HTTP requests to ManyChat API."""
        url = f"{self.BASE_URL}{endpoint}"
        try:
            async with httpx.AsyncClient() as client:
                response = await client.request(method, url, headers=self.headers, json=data)
                response_data = response.json()

                if response.status_code != 200 or response_data.get("status") != "success":
                    await log("error", f"ManyChat API failed - {function_name}", response=response_data)
                    return None

                return response_data

        except Exception as e:
            await log("error", f"ManyChat API Error - {function_name}", error=str(e), traceback=traceback.format_exc())

    async def send_message(self, subscriber_id, message):
        """Sends a message to a ManyChat subscriber."""
        return await self._request("POST", "/sending/sendContent", data={
            "subscriber_id": subscriber_id,
            "data": {"version": "v2", "content": {"type": "instagram", "messages": [{"type": "text", "text": message}]}},
            "message_tag": "ACCOUNT_UPDATE"
        }, function_name="send_message", subscriber_id=subscriber_id)

    async def add_tag(self, subscriber_id, tag_name):
        """Adds a tag to a ManyChat subscriber."""
        return await self._request("POST", "/tag/addTagByName", data={"subscriber_id": subscriber_id, "tag_name": tag_name},
                                   function_name="add_tag", subscriber_id=subscriber_id)

    async def remove_tag(self, subscriber_id, tag_name):
        """Removes a tag from a ManyChat subscriber."""
        return await self._request("POST", "/tag/removeTagByName", data={"subscriber_id": subscriber_id, "tag_name": tag_name},
                                   function_name="remove_tag", subscriber_id=subscriber_id)

    async def set_custom_field(self, subscriber_id, field_name, field_value):
        """Updates a custom field for a ManyChat subscriber."""
        return await self._request("POST", "/custom_field/setCustomFieldByName", data={
            "subscriber_id": subscriber_id, "field_name": field_name, "field_value": field_value
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
    """Handles AI conversation advancement."""
    try:
        run_response = await openai_client.beta.threads.runs.create_and_poll(
            thread_id=convo_data["thread_id"],
            assistant_id=convo_data["assistant_id"]
        )

        if not run_response:
            raise Exception("Run failed")

        await process_run_response(run_response, convo_data)

    except Exception as e:
        await log("error", "advance_convo - Unexpected error", error=str(e), traceback=traceback.format_exc())



async def process_run_response(run_response, convo_data):
    """Processes AI-generated responses."""
    run_status = run_response.status

    if run_status == "completed":
        await process_message_response(run_response, convo_data)
    elif run_status == "requires_action":
        await process_function_response(run_response, convo_data)
    else:
        await log("error", "Run thread failed", response=run_response)



async def process_message_response(run_response, convo_data):
    """Sends AI-generated messages to ManyChat."""
    try:
        ai_messages = await openai_client.beta.threads.messages.list(
            thread_id=convo_data["thread_id"], run_id=run_response.id
        )
        messages = ai_messages.data

        if not messages:
            await log("error", "No messages found in run response", convo_data=convo_data)
            return

        ai_content = messages[-1].content[0].text.value.split("【")[0]
        await mc_api.send_message(convo_data["manychat_id"], ai_content)

    except Exception as e:
        await log("error", "Error processing AI message response", error=str(e), traceback=traceback.format_exc())








# Actions
#
async def change_assistant(function_args, convo_data):
    """Updates the AI assistant scenario."""
    assistant_map = {
        "Italian": os.getenv("Italian_ASST"),
        "ecommerce": os.getenv("ecommerce_ASST"),
        "mainMenu": os.getenv("mainMenu_ASST")
    }
    new_assistant_id = assistant_map.get(function_args.get("scenario"))
    if new_assistant_id:
        await mc_api.set_custom_field(convo_data["manychat_id"], "assistant_id", new_assistant_id)


async def end_bot(function_args, convo_data):
    """Disables automated messages."""
    await mc_api.remove_tag(convo_data["manychat_id"], "auto message active")
    await mc_api.add_tag(convo_data["manychat_id"], "disable auto message")


async def log(level, msg, **kwargs):
    """Centralized logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))
