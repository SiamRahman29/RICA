import os
import httpx
import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException
from app.routes.manager.models import AskRequest, AskResponse

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
BOT_API = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
AGENT_ENDPOINT = os.environ["NGROK_URL"]
QUERY_ENDPOINT = f"{AGENT_ENDPOINT}/manager/ask"

router = APIRouter(prefix="/telegram", tags=["telegram"])


async def process_update(update: dict):
    message = update.get("message")
    if not message or "text" not in message:
        return

    chat_id = message["chat"]["id"]
    user_text = message["text"]

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # Construct request
            ask_request = AskRequest(query_text=user_text)
            
            logger.info(f"Sending request to: {QUERY_ENDPOINT}")
            logger.info(f"Request payload: {ask_request.model_dump()}")

            # Send to agent backend
            resp = await client.post(
                QUERY_ENDPOINT,
                json=ask_request.model_dump(),
            )
            logger.info(f"Response status: {resp.status_code}")
            resp.raise_for_status()

            # Parse response safely
            response_data = AskResponse(**resp.json())
            answer = response_data.response

            # Send reply back to Telegram
            await client.post(
                f"{BOT_API}/sendMessage",
                json={"chat_id": chat_id, "text": answer},
            )

    except Exception as e:
        logger.error(f"Error processing telegram message: {e}")
        logger.error(f"Query endpoint: {QUERY_ENDPOINT}")
        
        # Send fallback error message to user
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{BOT_API}/sendMessage",
                    json={"chat_id": chat_id, "text": "⚠️ Something went wrong. Please try again."},
                )
        except Exception as telegram_error:
            logger.error(f"Failed to send error message to Telegram: {telegram_error}")
        
        # Don't re-raise to avoid crashing the webhook handler
        # raise e


@router.post("/webhook")
async def telegram_webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    background_tasks.add_task(process_update, update)
    return {"ok": True}
