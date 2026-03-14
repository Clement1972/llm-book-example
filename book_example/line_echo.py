import os
from flask import Flask, request, abort

from linebot.v3.webhook import WebhookHandler
from linebot.v3.webhooks import MessageEvent, TextMessageContent
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
)

LINE_CHANNEL_ACCESS_TOKEN = "參照書本附錄申請LINE帳號的ACCESS_TOKEN"
LINE_CHANNEL_SECRET = "參照書本附錄申請LINE帳號的SECRET"

app = Flask(__name__)

configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

@app.route("/")
def read_root():
    return "This is a LINE BOT"


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        abort(400, str(e))

    return "OK"


# === main / handler ===
@handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    user_text = event.message.text

    # 👉 在 main 裡列印訊息
    print(f"[LINE MESSAGE] {user_text}")

    reply_text = f"你剛剛說：{user_text}"

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=reply_text)],
            )
        )

if __name__ == "__main__":
    # 教學 / 本機測試用
    app.run(host="0.0.0.0", port=5000, debug=True)
