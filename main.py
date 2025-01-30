from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
import json
import os
import traceback
from openai import AsyncOpenAI
import httpx
from actions import (
    end_bot,
    change_assistant,
    ManychatAPI
)

app = FastAPI()

# Initialize OpenAI client
openai_client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# Initialize ManyChat API client
mc_api = ManychatAPI()

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

        log("info", f"Request received -- {validated_fields.get('manychat_id', 'unknown')}", data=validated_fields)
        return {"status": "success"}
    except Exception as e:
        await log("error", f"generate_response -- Unexpected error --- {validated_fields.get('manychat_id', 'unknown')}", error=str(e), traceback=traceback.format_exc(), manychat_id=validated_fields.get("manychat_id", "unknown"))
        return {"status": "error"}







### Main endpoint functionality

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

        await openai_client.beta.threads.runs.submit_tool_outputs(
            thread_id=thread_id,
            run_id=run_id,
            tool_outputs=[{"tool_call_id": tool_call.id, "output": "success"}]
        )

        if "scenario" in function_args:
            await change_assistant(function_args, thread_id, manychat_id)
        
        elif "endDemo" in function_args:
            await end_demo(function_args, thread_id, manychat_id)
            
        else:
            await log("error", f"Unknown function response --- {manychat_id}", function_args=function_args, manychat_id=manychat_id)

    except Exception as e:
        await log("error", f"Error processing function response --- {manychat_id}", error=str(e), traceback=traceback.format_exc(), manychat_id=manychat_id)



async def log(level, msg, **kwargs):
    """Centralized logger for structured JSON logging."""
    print(json.dumps({"level": level, "msg": msg, **kwargs}))
