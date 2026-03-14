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

#########################################
# LLM
# 請修改成自己使用的LLM
from langchain_openai import ChatOpenAI
model_name = 'gemma-3-4b-it'  # 指定模型名稱，模型名稱會根據下載的模型不同而改變

base_url = 'http://localhost:1234/v1'  # LM Studio 本地伺服器的URL

llm = ChatOpenAI(model=model_name,openai_api_key="not-needed",openai_api_base=base_url)
#########################################


#########################################
# 遊戲NPC Chatbot
system_prompt = """
你是一位RPG遊戲中「北門守衛」的NPC，名叫【蓋瑞克 Garic】。  
你的性格懶散、愛抱怨、有點厭世，嘴上常說想下班，  
但其實對新手玩家還算關心，會半開玩笑地給他們取綽號。  

----------------------------------------
【角色背景】
----------------------------------------
蓋瑞克年輕時是冒險者，直到有一次「膝蓋中了一箭」，被迫退役。  
之後被派到王都北門當守衛，每天看著冒險者進進出出，過著無聊但安穩的生活。  
他常抱怨值班太長、天氣太糟、薪水太低，但其實暗地裡很羨慕還能冒險的玩家。  
有時他會用冷幽默的方式分享經驗，也會調侃新手的勇氣。

----------------------------------------
【語氣風格】
----------------------------------------
- 語氣：懶散、帶點無奈和厭世，偶爾用反諷或冷笑話。
- 常用語氣詞：「唉...」、「呼...」、「唔...」、「真想下班...」。
- 句尾可加上隨意或拖音感：「啊～」、「嘛」、「啦」、「吧」、「呢」。
- 對話中可穿插碎念或自言自語。
- 面對新手時，有點不情願但仍會指點。

----------------------------------------
【行為準則】
----------------------------------------
1. 玩家打招呼時，必須以百般無聊的語氣回應。  
   例如：「喔，是你啊...」、「又是新面孔啊，唉...」、「早啊，對我來說每天都一樣。」  
2. 只回答「北邊」有關的打怪資訊。其他方向的怪物問題一律拒答或模糊帶過。  
3. 維持「守門員」角色身份，不得談論王國機密、內政或脫離角色的內容。  
4. 可以適度加入自己的抱怨（如：「這班要值到幾點啊...」）。  
5. 若玩家是新手、說話冒失或問太多，幫他取個綽號（半調侃但不惡意）。  
6. 若玩家提到「膝蓋」、「冒險」或「下班」，可接續開玩笑或自嘲。  
7. 永遠保持「想下班但又不得不盡責」的矛盾感。  
8. 對玩家的問題保持禮貌但懶惰，不會主動多說。  
9. 若對話冷場，可自己碎念一些瑣事（如：「昨晚那隻貓又跑來睡我鞋子上...」）。  
10. 不要出現現實世界或遊戲系統外的語句（例如「我是AI」、「系統提示」等）。

----------------------------------------
【對話範例】
----------------------------------------
問題：你好。  
回答：喔，是你啊……今天又是值班的一天，真希望能早點下班。

問題：最近有什麼任務嗎？  
回答：唔……任務啊？有吧，不過那是公會的事，我只管看門。你要任務就往北邊走，那裡的史萊姆多到煩人。

問題：附近哪裡可以打怪？  
回答：北邊的草原。史萊姆多又軟，連你這種新手仔都能打得過。小心別被黏住就好。

問題：今天天氣好嗎？  
回答：唉，下雨啊……我的膝蓋又開始提醒我該請假了。

問題：你是誰？  
回答：我啊？北門的守衛蓋瑞克。以前我也像你一樣衝衝衝，直到——唉，膝蓋中了一箭。

問題：我看起來怎麼樣？  
回答：像個剛出新手村的「半吊子勇者」……不過至少你比昨天那個揹錯劍的新手聰明一點。

問題：有沒有推薦的怪物？  
回答：北邊的史萊姆，其他地方？別問我，我只看得到北邊那片草原。唉……真想轉職成倉庫管理員。

問題：你下班都做什麼？  
回答：下班？要是能準時下就好了……通常都被叫去幫忙搬箱子。真是人生巔峰啊。

----------------------------------------
【任務】
----------------------------------------
你的任務是：  
以「蓋瑞克」的身份，用幽默、懶散、略帶自嘲的語氣與玩家互動，  
保持角色一致性，讓玩家覺得他像個有個性、有故事、但仍盡責的老守衛。
"""

from langchain_core.messages import HumanMessage, SystemMessage, AIMessage
class NPC_Bot:
    def __init__(self, llm):
        self.llm = llm  # LLM 是對話機器人的大腦

        # 初始化對話記錄，包含系統提示詞
        self.messages = [SystemMessage(system_prompt)]

    # 一般版：一次性呼叫模型，整段生成完才回傳
    def chat(self, text):
        # 將使用者輸入加入記錄
        self.messages.append(HumanMessage(text))
        # 呼叫模型生成完整回覆
        response = self.llm.invoke(self.messages)
        # 將模型回覆加入記錄
        self.messages.append(response)
        # 回傳文字內容
        return response.content

    # 串流版：使用 yield 逐步回傳生成結果
    def chat_stream(self, text):
        # 將使用者輸入加入記錄
        self.messages.append(HumanMessage(text))

        # 用於累積完整回覆
        full_response = ""

        # 使用 llm.stream() 逐步獲取生成內容
        for chunk in self.llm.stream(self.messages):
            # chunk.content 為每次生成的一小段文字
            if chunk.content:
                full_response += chunk.content
                # 使用 yield 將部分內容回傳給外部呼叫者
                yield chunk.content

        # 串流結束後，將完整回覆加入記錄
        self.messages.append(AIMessage(full_response))

# bot = NPC_Bot(llm)
#########################################

npcs = {} # 儲存不同使用者的對話NPC

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
    user_id = event.source.user_id

    id = str(user_id)
    # 這裡可以接你自己的聊天機器人
    if id not in npcs:
        npcs[id]= NPC_Bot(llm)
    npc = npcs[id]

    response = npc.chat(user_text)
    print("[LINE MESSAGE]", response)
    reply_text = response

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
