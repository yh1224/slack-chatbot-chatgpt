import json
import logging
import os

from openai import OpenAI
from slack_bolt import App, Ack, Say
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

LOG_LEVEL = os.environ.get("LOG_LEVEL")

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_BOT_MEMBER_ID = os.environ.get("SLACK_BOT_MEMBER_ID")

CHATGPT_SETTINGS = os.environ.get("CHATGPT_SETTINGS")

logging.getLogger(__name__).setLevel(LOG_LEVEL)

app = App(
    logger=logging.getLogger(__name__),
    signing_secret=SLACK_SIGNING_SECRET,
    token=SLACK_BOT_TOKEN,
)


def send_ack(ack: Ack):
    ack()


def get_thread_ts(channel_id: str, event_ts: str) -> str:
    res = app.client.conversations_replies(
        channel=channel_id,
        ts=event_ts,
        limit=1,
    )
    messages = res["messages"]
    if "ok" in res and "thread_ts" in messages[0]:
        return messages[0]["thread_ts"]
    else:
        return event_ts


def get_thread_messages(channel_id, thread_ts: str, limit: int) -> list[dict]:
    res = app.client.conversations_replies(
        channel=channel_id,
        ts=thread_ts,
        limit=limit,
    )
    return res["messages"]


def handle_app_mentions(event, say: Say, logger: logging.Logger):
    logger.debug("event: %s", json.dumps(event, ensure_ascii=False))
    channel_id = event["channel"]
    event_ts = event["event_ts"]

    # get messages
    thread_messages = get_thread_messages(channel_id, get_thread_ts(channel_id, event_ts), 30)
    logger.debug(json.dumps(thread_messages, ensure_ascii=False))

    # ask
    inputs: list[dict] = []
    for m in thread_messages:
        if m["user"] == SLACK_BOT_MEMBER_ID:
            inputs.append({"role": "assistant", "content": m["text"]})
        elif m["text"].startswith(f"<@{SLACK_BOT_MEMBER_ID}>"):
            text = m["text"].replace(f"<@{SLACK_BOT_MEMBER_ID}>", "").strip()
            inputs.append({"role": "user", "content": text})
    # logger.debug(f"Using ChatGPT: {CHATGPT_SETTINGS}")
    logger.debug(json.dumps(inputs))

    settings = json.loads(CHATGPT_SETTINGS)
    client = OpenAI(api_key=settings["apiKey"])
    response = client.chat.completions.create(
        model=settings["model"],
        messages=inputs,
    )
    result = response.choices[0].message.content

    # reply
    say(channel=channel_id, thread_ts=event_ts, text=result)


app.event("app_mention")(
    ack=send_ack,
    lazy=[handle_app_mentions],
)


def lambda_handler(event, context):
    slack_handler = SlackRequestHandler(app=app)
    headers = {k.lower(): v for k, v in event["headers"].items()}
    if "x-slack-retry-num" in headers and int(headers["x-slack-retry-num"]) > 0:
        print("Retry request ignored")
        return {"statusCode": 200, "body": "Retry request ignored"}
    return slack_handler.handle(event, context)
