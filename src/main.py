import json
import logging
import os
import time

from openai import OpenAI
from slack_bolt import App, Ack, Say
from slack_bolt.adapter.aws_lambda import SlackRequestHandler

LOG_LEVEL = os.environ.get("LOG_LEVEL")

SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET")
SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN")
SLACK_BOT_MEMBER_ID = os.environ.get("SLACK_BOT_MEMBER_ID")

CHATGPT_SETTINGS = os.environ.get("CHATGPT_SETTINGS")

STREAM_INTERVAL = 3  # 3 秒間隔でメッセージを更新
STREAM_TEXT_THINKING = "Thinking..."
STREAM_TEXT_MORE = "•"

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

    # build inputs
    inputs: list[dict] = []
    for m in thread_messages:
        if m["user"] == SLACK_BOT_MEMBER_ID:
            inputs.append({"role": "assistant", "content": m["text"]})
        elif m["text"].startswith(f"<@{SLACK_BOT_MEMBER_ID}>"):
            text = m["text"].replace(f"<@{SLACK_BOT_MEMBER_ID}>", "").strip()
            inputs.append({"role": "user", "content": text})
    # logger.debug(f"Using ChatGPT: {CHATGPT_SETTINGS}")
    logger.debug(json.dumps(inputs))

    # ask
    settings = json.loads(CHATGPT_SETTINGS)
    client = OpenAI(api_key=settings["apiKey"])
    started = time.time()
    if settings.get("stream", False):
        # streaming mode
        message = say(channel=channel_id, thread_ts=event_ts, text=STREAM_TEXT_THINKING)

        response = client.chat.completions.create(
            model=settings["model"],
            messages=inputs,
            stream=True,
            stream_options={"include_usage": True},
        )
        result = ""
        checkpoint = time.time()
        usage = None
        for chunk in response:
            if len(chunk.choices) > 0:
                content = chunk.choices[0].delta.content
                if content:
                    result += content
                    elapsed = time.time() - checkpoint
                    if elapsed > STREAM_INTERVAL:
                        app.client.chat_update(
                            channel=channel_id,
                            ts=message["ts"],
                            text=result + STREAM_TEXT_MORE,
                        )
                        checkpoint = time.time()
            if chunk.usage:
                usage = chunk.usage
        total = time.time() - started
        result += f"\n\nelapsed: {total:.2f} seconds"
        if usage:
            result += f"\nprompt tokens: {usage.prompt_tokens}"
            result += f"\ncompletion tokens: {usage.completion_tokens}"
        app.client.chat_update(
            channel=channel_id,
            ts=message["ts"],
            text=result,
        )
    else:
        # not streaming mode
        response = client.chat.completions.create(
            model=settings["model"],
            messages=inputs,
        )
        result = response.choices[0].message.content
        total = time.time() - started
        result += f"\n\nelapsed: {total:.2f} seconds"
        if response.usage:
            result += f"\nprompt tokens: {response.usage.prompt_tokens}"
            result += f"\ncompletion tokens: {response.usage.completion_tokens}"
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
