from langchain_google_genai import ChatGoogleGenerativeAI

API_KEY = "這邊請改成你自己的API_KEY值"
model_name = 'gemini-2.5-flash'

llm = ChatGoogleGenerativeAI(
    model=model_name,
    google_api_key=API_KEY
)


from langchain_core.tools import tool

# 匯入 geopy 套件中的 Nominatim 類別，用於地理編碼（將地名轉換成經緯度）
from geopy.geocoders import Nominatim, ArcGIS

# 定義函式：輸入城市名稱，回傳其經緯度座標
@tool 
def tool_get_coordinates(city_name: str):
    """取得城市GPS座標，先用 Nominatim，失敗時改用 ArcGIS"""

    # ---- 第一來源：Nominatim ----
    try:
        geolocator1 = Nominatim(user_agent="clement_fallback_test")
        location = geolocator1.geocode(city_name, timeout=10)

        if location:
            return (location.latitude, location.longitude)
    except:
        pass  # 忽略錯誤，直接進入第二來源

    # ---- 第二來源：ArcGIS ----
    try:
        geolocator2 = ArcGIS(timeout=10)
        location = geolocator2.geocode(city_name)

        if location:
            return (location.latitude, location.longitude)
    except Exception as e:
        return e

    return None

# 匯入 requests 套件，用於發送 HTTP 請求
import requests

# 定義函式：輸入經緯度，回傳目前天氣資訊（溫度）
@tool 
def tool_get_weather(latitude: float, longitude: float):
    """取得溫度值

    Args:
        latitude: GPS經度
        longitude: GPS緯度
    """    

    # 使用 Open-Meteo API 發送 GET 請求，取得氣象資料
    # API 參數：
    # - latitude / longitude: 經緯度
    # - current: 取得目前時刻的溫度 (temperature_2m) 與風速 (wind_speed_10m)
    # - hourly: 取得每小時溫度、相對濕度、風速
    response = requests.get(
        f"https://api.open-meteo.com/v1/forecast?"
        f"latitude={latitude}&longitude={longitude}&"
        f"current=temperature_2m,wind_speed_10m&"
        f"hourly=temperature_2m,relative_humidity_2m,wind_speed_10m"
    )

    # 將回傳的 JSON 資料解析成 Python 字典
    data = response.json()

    # 回傳目前時刻的氣溫（單位：攝氏度）
    return data['current']['temperature_2m']


from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.output_parsers import StrOutputParser

class chat_bot:
    def __init__(self, llm, tools):
        # 初始化對話機器人，傳入 LLM 與可用工具列表
        self.tools = tools
        # 將 LLM 綁定（bind）工具，使其具備自動呼叫工具的能力
        self.llm_with_tools = llm.bind_tools(tools)

        # 系統提示詞（System Prompt），用來設定 LLM 的角色與行為
        system_prompt = '''
你是一位智慧型個人助理，能夠根據使用者的問題主動判斷是否需要使用工具。
請以清楚、簡潔的方式回答問題。
若問題需要外部資料，請直接使用可用的工具完成查詢，不需向使用者確認。
'''        
        # 初始化訊息列表，第一條訊息是系統指令
        self.message = [SystemMessage(system_prompt)]

        # 將 LLM 的回應解析為純文字格式的工具
        self.str_parser = StrOutputParser()
       
    def chat_generator(self, text):
        """
        主對話生成函式（生成器形式）。
        逐步執行 LLM 回應與工具調用，並即時回傳每一步的結果。
        """
        # 將使用者的輸入加入訊息列表
        self.message.append(HumanMessage(text))        
        
        while True:
            # 呼叫 LLM，傳入完整訊息歷史
            response = self.llm_with_tools.invoke(self.message)
            # 將 LLM 回應加入訊息列表
            self.message.append(response)

            # 檢查 LLM 是否要求呼叫工具
            is_tools_call = False
            for tool_call in response.tool_calls:
                is_tools_call = True

                # 顯示 LLM 要執行的工具名稱與參數
                msg = f'【執行】: {tool_call["name"]}({tool_call["args"]})\n'
                yield msg  # 使用 yield 讓結果能即時顯示在輸出中

                # 實際執行工具（根據工具名稱動態呼叫對應物件）
                tool_result = globals()[tool_call['name']].invoke(tool_call['args'])

                # 顯示工具執行結果
                msg = f'【結果】: {tool_result}\n'
                yield msg

                # 將工具執行結果封裝成 ToolMessage 回傳給 LLM
                tool_message = ToolMessage(
                    content=str(tool_result),          # 工具執行的文字結果
                    name=tool_call["name"],            # 工具名稱
                    tool_call_id=tool_call["id"],      # 工具呼叫 ID（讓 LLM 知道對應哪個呼叫）
                )
                # 將工具回傳結果加入訊息列表，提供 LLM 下一輪參考
                self.message.append(tool_message)
            
            # 若這一輪沒有任何工具呼叫，表示 LLM 已經生成最終回覆
            if is_tools_call == False:
                # 將 LLM 回應解析成純文字並輸出
                yield self.str_parser.invoke(response)
                return  # 結束對話流程

    def chat(self, text):
        """
        封裝版對話函式。
        會收集 chat_generator 的所有輸出，並組合成完整的回覆字串。
        """
        msg = ''
        # 逐步取得 chat_generator 的產出內容
        for chunk in self.chat_generator(text):
            msg += f"{chunk}"
        # 回傳最終組合的對話內容
        return msg


import gradio as gr

# 建立 chat_bot 物件，並將 LLM 以及兩個工具（get_coordinates, get_weather）傳入
# 這樣 LLM 在回答時就能自動選擇使用這些工具
bot = chat_bot(llm, [tool_get_coordinates, tool_get_weather])

# 定義一個用於 Gradio 聊天介面的函式
# message：使用者輸入的訊息
# history：對話歷史（Gradio 會自動傳入）
def chat_function(message, history):
    partial_response = ""  # 用來累積 LLM 的回應文字
    # chat_generator 是一個生成器 (generator)，會逐步產生模型或工具執行的輸出
    for chunk in bot.chat_generator(message):
        partial_response += f'{chunk}'  # 將每個輸出逐步串起來
        yield partial_response  # 即時回傳當前的部分結果，讓介面可以即時顯示

# 建立 Gradio 的聊天介面
# - chat_function：處理每次使用者輸入的函式
# - type="messages"：Gradio 會自動顯示成對話形式
demo = gr.ChatInterface(chat_function)

# 主程式進入點
# 啟動 Gradio Web 介面
if __name__ == "__main__":
    demo.launch()


