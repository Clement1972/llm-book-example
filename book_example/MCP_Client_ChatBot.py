import asyncio
import json
import os
import sys
from mcp import ClientSession, StdioServerParameters
from contextlib import AsyncExitStack  # 用於管理多個動態的非同步 Context Manager
from mcp.client.stdio import stdio_client
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.output_parsers import StrOutputParser
import gradio as gr
from langchain_google_genai import ChatGoogleGenerativeAI

# =================配置區=================
# 注意：在實際專案中，建議將 API Key 放在環境變數 (.env) 中，避免寫死在程式碼裡
API_KEY = "這邊請改成你自己的API_KEY值" 
model_name = 'gemini-2.5-flash'

llm = ChatGoogleGenerativeAI(
    model=model_name,
    google_api_key=API_KEY
)

def load_config(filename):
    """
    載入設定檔函式。
    強制從腳本 (.py) 所在的絕對路徑讀取 JSON，避免因執行目錄不同而找不到檔案。
    """
    # 1. 獲取當前腳本的目錄路徑
    # sys.argv[0] 是腳本名稱，os.path.abspath 轉為絕對路徑，os.path.dirname 取出目錄
    current_script_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    
    # 2. 組合出完整的檔案路徑 (自動處理 Windows/Linux 路徑分隔符號)
    file_path = os.path.join(current_script_dir, filename)

    print(f"嘗試讀取設定檔路徑: {file_path}")

    # 3. 讀取檔案與錯誤處理
    try:
        if not os.path.exists(file_path):
            print(f"錯誤：找不到檔案 '{filename}'，請確認它與腳本在同一個目錄下。")
            return None

        with open(file_path, 'r', encoding='utf-8') as file:
            config_dict = json.load(file)
            return config_dict

    except json.JSONDecodeError as e:
        print(f"錯誤：JSON 格式解析失敗。\n詳細訊息: {e}")
        return None
    except Exception as e:
        print(f"發生未預期的讀取錯誤: {e}")
        return None


class mcp_client_chat_bot:
    def __init__(self, llm, server_params_list):
        """
        初始化 ChatBot 實例
        :param llm: LangChain 的 LLM 物件
        :param server_params_list: MCP Server 的連線參數列表
        """
        self.server_params_list = server_params_list
        self.llm = llm
        self.llm_with_tools = None
        self.tools_by_name = {}
        # AsyncExitStack 用於管理動態數量的上下文管理器 (Context Managers)
        # 它可以確保在程式結束或發生錯誤時，所有的 MCP 連線都能被正確關閉
        self.exit_stack = AsyncExitStack()        

        # 設定系統提示詞 (System Prompt)，定義 AI 的行為模式
        system_prompt = '''
你是一位智慧型個人助理，能夠根據使用者的問題主動判斷是否需要使用工具。
請以清楚、簡潔的方式回答問題。
若問題需要外部資料，請直接使用可用的工具完成查詢，不需向使用者確認。
'''        
        # 初始化對話歷史，首條訊息為系統設定
        self.message = [SystemMessage(system_prompt)]

        # 用於解析 LLM 的純文字回應
        self.str_parser = StrOutputParser()
       
    async def __mcp_init(self):
        """
        初始化 MCP 連線與工具載入 (Lazy Loading 模式)
        此函式只會執行一次，若已初始化則直接返回。
        """
        if self.llm_with_tools is not None:
            return

        all_tools = []

        print("正在初始化 MCP Server 連線...")
        try:
            for server_params in self.server_params_list:
                # 1. 建立 stdio 傳輸層的上下文
                stdio = stdio_client(server_params)
                # 使用 exit_stack 進入 context，這等同於 'async with stdio as (read, write):'
                # 但這樣寫允許我們同時開啟多個 server 連線而不需巢狀縮排
                read, write = await self.exit_stack.enter_async_context(stdio)

                # 2. 建立 MCP Client Session 上下文            
                session = ClientSession(read, write)
                await self.exit_stack.enter_async_context(session)

                # 3. 初始化 Session 握手協議
                await session.initialize()

                # 4. 透過 LangChain Adapter 載入該 Server 提供的所有工具
                tools = await load_mcp_tools(session)
                all_tools.extend(tools)

            print(f"MCP Server 初始化成功，共載入 {len(all_tools)} 個工具。")

            # 將工具綁定到 LLM 模型上 (Function Calling 功能)
            self.llm_with_tools = self.llm.bind_tools(all_tools)
            # 建立工具名稱對照表，方便後續快速查找與執行
            self.tools_by_name = {tool.name: tool for tool in all_tools}

        except Exception as e:
            print(f"MCP Server 初始化失敗: {e}")
            await self.close() # 若初始化過程失敗，確保釋放已佔用的資源
            raise e

    async def close(self):
        """
        安全關閉所有資源
        會依序觸發 exit_stack 中所有已註冊 context 的 __aexit__ 方法
        """
        print("正在關閉 MCP 連線與釋放資源...")
        await self.exit_stack.aclose()
        print("MCP 連線已完全關閉。")

    async def chat_generator(self, text):
        """
        核心對話生成器 (Generator)
        負責處理：使用者輸入 -> LLM 思考 -> (可選) 執行工具 -> LLM 最終回應
        使用 yield 實現串流 (Streaming) 輸出。
        """
        await self.__mcp_init()
        
        # 將使用者的最新輸入加入對話歷史
        self.message.append(HumanMessage(text))        
        
        while True:
            # 1. 呼叫 LLM，傳入完整的對話歷史
            final_ai_message = AIMessageChunk(content="")
            
            # 使用 stream 模式逐步接收 LLM 的回應
            for chunk in self.llm_with_tools.stream(self.message):
                final_ai_message += chunk
                # 如果有點文字內容，就即時回傳給前端顯示
                if hasattr(chunk, 'content') and chunk.content:
                    yield self.str_parser.invoke(chunk)
            
            response = final_ai_message
            
            # 將 LLM 的完整回應 (包含文字或工具呼叫請求) 加入歷史記錄
            self.message.append(response)

            # 2. 判斷 LLM 是否想要呼叫工具
            if not response.tool_calls:
                return # 若沒有工具呼叫，代表對話回應完成，跳出迴圈

            # 3. 處理工具呼叫 (可能一次呼叫多個工具)
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]                
                
                # 提示訊息：告知使用者正在執行什麼工具
                msg = f'\n【系統執行工具】: {tool_name}({tool_args})\n'
                yield msg 

                # 根據名稱查找對應的工具物件
                if tool_name in self.tools_by_name:
                    selected_tool = self.tools_by_name[tool_name]
                    try:
                        # 實際執行工具 (非同步執行)
                        tool_result = await selected_tool.ainvoke(tool_args)
                    except Exception as e:
                        tool_result = f"執行錯誤: {str(e)}"
                else:
                    tool_result = f"Error: Tool {tool_name} not found."

                # 提示訊息：顯示工具執行結果
                msg = f'【工具執行結果】: {tool_result}\n'
                yield msg

                # 4. 建構 ToolMessage 回傳給 LLM
                # 這是必要的，讓 LLM 知道工具執行的結果，以便它根據結果生成最終回答
                tool_message = ToolMessage(
                    content=str(tool_result),          # 工具的輸出內容
                    name=tool_call["name"],            # 工具名稱
                    tool_call_id=tool_call["id"],      # 必須對應原始呼叫的 ID
                )
                self.message.append(tool_message)
            
            # 迴圈繼續：帶著工具的結果，再次呼叫 LLM (回到 while True 開頭)
            

    async def chat(self, text):
        """
        非串流的對話接口 (封裝用)。
        如果不需要打字機效果，可以使用此函式直接獲取完整回應。
        """
        msg = ''
        async for chunk in self.chat_generator(text):
            msg += f"{chunk}"
        return msg


async def main():
    config_file = 'MCP_Client_Config.json'
    
    # 載入設定
    config_data = load_config(config_file)

    if config_data is None:
        print("設定檔讀取失敗，程式終止。")
        return 

    print('=== MCP Servers 設定 ===')
    server_params = []
    # 解析 JSON 設定，轉換為 MCP SDK 需要的 StdioServerParameters 物件
    for key, value in config_data["mcpServers"].items():
        server_params.append(
            StdioServerParameters(command=value["command"], args=value["args"], env=None)
        )
        print(f"  - Server: {key} | Command: {value['command']} {value['args']}")        

    # 建立 ChatBot 實體
    bot = mcp_client_chat_bot(llm, server_params)

    # 定義 Gradio 的介面函式
    async def chat_function(message, history):
        partial_response = ""  # 用於累積回應文字
        # 透過 async for 接收生成器的串流輸出
        async for chunk in bot.chat_generator(message):
            partial_response += f'{chunk}' 
            yield partial_response  # Gradio 會即時更新 UI 內容
    
    # 啟動 Gradio 網頁介面
    demo = gr.ChatInterface(chat_function, autofocus=False, title="MCP 智慧助理")
    print("啟動 Gradio 伺服器...")
    
    # launch() 預設是阻塞的 (blocking)，直到網頁伺服器關閉才會繼續往下執行
    demo.launch()
    
    # 當 Gradio 關閉後，執行資源清理
    await bot.close()


if __name__ == "__main__":
    asyncio.run(main())