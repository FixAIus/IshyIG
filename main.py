from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
import json
import os
import traceback
from openai import AsyncOpenAI
import httpx

app = FastAPI()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@app.post("/generateResponse")
async def generate_response(request: Request, background_tasks: BackgroundTasks):
    try:
        # Parse request data
        data = await request.json()

        # Validate fields
        validated_fields = await validate_request_data(data)
        if not validated_fields:
            raise HTTPException(status_code=400, detail="Invalid request data")

        # Add background task to advance the conversation
        background_tasks.add_task(advance_convo, validated_fields)

        return {"status": "success"}
    except Exception as e:
        await log("error", "generate_response -- Unexpected error", error=str(e), traceback=traceback.format_exc())
        return {"status": "error"}

async def validate_request_data(data):
    """Validate request data for required fields."""
    try:
        required_fields = ["thread_id", "assistant_id", "bot_filter_tag", "manychat_id"]
        fields = {field: data.get(field) for field in required_fields}
        missing_fields = [field for field in required_fields if not fields[field] or fields[field] in ["", "null", None]]

        if missing_fields:
            await log("error", "Missing fields", missing_fields=missing_fields, received_fields=data)
            return None

        return fields
    except Exception as e:
        await log("error", "Validation error", error=str(e), traceback=traceback.format_exc())
        return None

async def advance_convo(convo_data):
    """Background task to handle conversation advancement."""
    try:
        thread_id = convo_data.get("thread_id")
        assistant_id = convo_data.get("assistant_id")
        bot_filter_tag = convo_data.get("bot_filter_tag")
        manychat_id = convo_data.get("manychat_id")

        # Run AI thread
        run_response = await openai_client.threads.runs.create_and_poll(
            thread_id=thread_id,
            assistant_id=assistant_id
        )

        if not run_response:
            await handle_bot_failure("Bot failure", bot_filter_tag)
            return

        # Process the AI response
        await process_run_response(run_response, thread_id, bot_filter_tag, manychat_id)

    except Exception as e:
        await log("error", "advance_convo -- Unexpected error", error=str(e), traceback=traceback.format_exc())

async def process_run_response(run_response, thread_id, bot_filter_tag, manychat_id):
    """Process the AI thread response."""
    try:
        run_status = run_response.status

        if run_status == "completed":
            await send_response_to_manychat(run_response, thread_id, manychat_id)
        elif run_status == "requires_action":
            await handle_action_required(run_response)
        else:
            await log("error", "Run thread failed", response=run_response)

    except Exception as e:
        await log("error", "process_run_response -- Unexpected error", error=str(e), traceback=traceback.format_exc())

async def send_response_to_manychat(run_response, thread_id, manychat_id):
    """Send AI response to ManyChat."""
    try:
        run_id = run_response.id
        ai_messages = await openai_client.beta.threads.messages.list(thread_id=thread_id, run_id=run_id)
        ai_messages = ai_messages.data

        if not ai_messages:
            await log("error", "No messages found in run response.")
            return

        # Extract the content of the last message
        ai_content = ai_messages[-1].content[0].text.value
        if "【" in ai_content and "】" in ai_content:
            ai_content = ai_content[:ai_content.find("【")] + ai_content[ai_content.find("】") + 1:]

        # Format the payload for ManyChat
        payload = {
            "subscriber_id": manychat_id,
            "data": {
                "version": "v2",
                "content": {
                    "type": "instagram",
                    "messages": [
                        {
                            "type": "text",
                            "text": ai_content
                        }
                    ]
                }
            },
            "message_tag": "ACCOUNT_UPDATE"
        }

        # Send the message to ManyChat API
        api_key = os.getenv("MANYCHAT_API_KEY")
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        async with httpx.AsyncClient() as client:
            response = await client.post("https://api.manychat.com/fb/sending/sendContent", json=payload, headers=headers)

        if response.status_code != 200:
            await log("error", "Failed to send message to ManyChat", status_code=response.status_code, response_text=response.text)

    except Exception as e:
        await log("error", "Error sending message to ManyChat", error=str(e), traceback=traceback.format_exc())

async def handle_bot_failure(reason, bot_filter_tag):
    """Handle bot failure by logging and performing cleanup actions."""
    await log("error", "Bot failure", reason=reason, bot_filter_tag=bot_filter_tag)

async def handle_action_required(run_response):
    """Handle scenarios where the run requires additional actions."""
    await log("info", "Action required for run", response=run_response)

async def log(level, msg, **kwargs):
    """Centralized logger for structured JSON logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))
