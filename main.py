from fastapi import FastAPI, BackgroundTasks, HTTPException, Request
import traceback
from utils import log
from actions import (
    openai_client,
    validate_request_data,
    advance_convo,
    process_run_response,
    process_message_response,
    change_assistant,
    end_bot
)
from ManychatAPI import mc_api


app = FastAPI()


@app.post("/generateResponse")
async def generate_response(request: Request, background_tasks: BackgroundTasks):
    """Handles incoming AI requests and triggers background processing."""
    try:
        data = await request.json()
        validated_fields = await validate_request_data(data)

        if not validated_fields:
            raise HTTPException(status_code=400, detail="Invalid request data")

        background_tasks.add_task(advance_convo, validated_fields)
        await log("info", f"Request received --- {validated_fields['manychat_id']}", data=validated_fields)

        return {"status": "success"}

    except Exception as e:
        await log("error", "generate_response - Unexpected error", error=str(e), traceback=traceback.format_exc())
        return {"status": "error"}
