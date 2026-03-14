from langchain_google_genai import ChatGoogleGenerativeAI

API_KEY = "這邊請改成你自己的API_KEY值"
model_name = 'gemini-2.5-flash'

llm = ChatGoogleGenerativeAI(
    model=model_name,
    google_api_key=API_KEY
)

# 專為 LLM 使用的工具集合（tools）
import os
from langchain_core.tools import tool
from pydantic import BaseModel, Field
import subprocess
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.document_loaders import UnstructuredWordDocumentLoader
from langchain_community.document_loaders import UnstructuredExcelLoader

# ------------------------------------------------------------
# 注意事項（給 LLM 與開發者）
# - 下列工具會在「工具可存取的根目錄」下執行所有檔案存取動作。
# - 所有函數在進行檔案/資料夾路徑操作時都會做絕對路徑檢查，防止跳脫根目錄。
# - 工具回傳文字或錯誤字串（錯誤會以中文訊息回報），以便 LLM 判斷下一步。
# - 工具設計時假定輸入是由 LLM 產生的參數（例如：檔名、子資料夾名稱），因此在 docstring 中用簡潔且結構化的格式說明用途與限制。
# ------------------------------------------------------------

# 設定（程式內變數）
ROOT_DIR = "C:/DATA/TEST"

# -------------------------------
# 型別定義（Pydantic schema）
# -------------------------------
class file_list_input(BaseModel):
    relative_path: str = Field(description="子資料夾名稱。可為空字串，代表根目錄。")

class read_txt_file_input(BaseModel):
    filename: str = Field(description="要讀取的文字檔相對路徑（相對於工具可存取的根目錄）。")

class save_txt_file_input(BaseModel):
    filename: str = Field(description="要儲存的文字檔相對路徑（相對於工具可存取的根目錄）。")
    content: str = Field(description="要寫入的文字內容。")

class run_python_input(BaseModel):
    filename: str = Field(description="要執行的 Python 檔案相對路徑（相對於工具可存取的根目錄）。")

class read_pdf_file_input(BaseModel):
    filename: str = Field(description="要讀取的 PDF 檔相對路徑（相對於工具可存取的根目錄）。")

class read_docx_file_input(BaseModel):
    filename: str = Field(description="要讀取的 Word (.docx) 檔相對路徑（相對於工具可存取的根目錄）。")

class read_xlsx_file_input(BaseModel):
    filename: str = Field(description="要讀取的 Excel (.xlsx) 檔相對路徑（相對於工具可存取的根目錄）。")

# ------------------------------------------------------------
# 協助函式
# ------------------------------------------------------------

def _abs_and_check(path: str) -> (str, str):
    """
    取得絕對路徑並檢查是否仍在工具可存取的根目錄內。

    Args:
        path: 相對路徑或完整路徑（相對於工具可存取的根目錄）。

    Returns:
        (abs_path, abs_root): 回傳絕對路徑與根目錄的絕對路徑。

    Notes:
        - 這個 helper 只負責計算與回傳，實際的允許/拒絕由呼叫端處理，以維持錯誤訊息的一致性。
    """
    abs_path = os.path.abspath(os.path.join(ROOT_DIR, path))
    abs_root = os.path.abspath(ROOT_DIR)
    return abs_path, abs_root


def document_to_txt(documents):
    """
    將文件 loader 回傳的多個 Document 物件合併成純文字。

    Args:
        documents: 一個可疊代的物件，每個元素具有 .page_content 屬性。

    Returns:
        字串：以換行符號連接每一頁的內容。
    """
    return "".join([doc.page_content for doc in documents])

# ==============================================================
# TOOL: 列出指定子資料夾的檔案
# ==============================================================

@tool("file_list", args_schema=file_list_input)
def file_list(relative_path=""):
    """
    列出「工具可存取的根目錄/relative_path」底下的檔案與子資料夾清單。

    Args:
        relative_path (str): 子資料夾相對路徑；空字串代表根目錄。

    Returns:
        dict:
            {
                "files": [檔案名稱...],
                "folders": [子資料夾名稱...]
            }
        或錯誤訊息字串。

    Error behavior:
        - 若路徑不在工具可存取的根目錄內，回傳錯誤字串。
        - 若資料夾不存在或無法存取，回傳對應的錯誤字串。

    安全限制：
        僅能列出根目錄底下的內容，禁止任何試圖跳脫根目錄的請求。
    """

    # 1) 取得絕對路徑（並透過 _abs_and_check 檢查合法性）
    abs_folder, abs_root = _abs_and_check(relative_path)

    # 2) 路徑安全檢查：禁止跳脫根目錄
    if not abs_folder.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的路徑！({relative_path})"

    # 3) 列出檔案與資料夾
    try:
        items = os.listdir(abs_folder)
        files = [
            f for f in items
            if os.path.isfile(os.path.join(abs_folder, f))
        ]
        folders = [
            d for d in items
            if os.path.isdir(os.path.join(abs_folder, d))
        ]

        return {
            "files": files,
            "folders": folders
        }

    except FileNotFoundError:
        return f"找不到資料夾: {abs_folder}"
    except PermissionError:
        return f"沒有權限讀取資料夾: {abs_folder}"
# ==============================================================
# TOOL: 讀取文字檔內容
# ==============================================================

@tool("read_txt_file", args_schema=read_txt_file_input)
def read_txt_file(filename):
    """
    讀取文字檔內容，並以 UTF-8 解碼後回傳整個文字內容。

    Args:
        filename (str): 相對路徑（相對於工具可存取的根目錄）。

    Returns:
        str: 檔案內容，或錯誤訊息字串。

    Error behavior:
        - 若嘗試跳脫根目錄，回傳錯誤字串。
        - 找不到檔案、權限問題或編碼錯誤，皆回傳對應的錯誤字串。

    安全限制：
        僅允許在工具可存取的根目錄下讀取檔案。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    try:
        # 明確指定 UTF-8，遇到不同編碼會回傳清楚錯誤訊息
        with open(abs_file, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return f"找不到檔案: {abs_file}"
    except PermissionError:
        return f"沒有權限讀取檔案: {abs_file}"
    except UnicodeDecodeError:
        return f"檔案編碼錯誤，無法以 UTF-8 讀取: {abs_file}"

# ==============================================================
# TOOL: 儲存文字檔
# ==============================================================

@tool("save_txt_file", args_schema=save_txt_file_input)
def save_txt_file(filename, content):
    """
    將文字內容寫入指定檔案（覆蓋既有檔案），若父資料夾不存在則自動建立。

    Args:
        filename (str): 相對路徑（相對於工具可存取的根目錄）。
        content (str): 要寫入的文字內容。

    Returns:
        str: 成功訊息或錯誤訊息字串。

    Error behavior:
        - 若嘗試跳脫根目錄或無寫入權限，回傳錯誤字串。
        - 其他檔案系統錯誤會以 OSError 的字串形式回傳。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    # 確保父資料夾存在
    os.makedirs(os.path.dirname(abs_file), exist_ok=True)

    try:
        with open(abs_file, "w", encoding="utf-8") as f:
            f.write(content)
        return f"成功儲存檔案: {abs_file}"
    except PermissionError:
        return f"沒有權限寫入檔案: {abs_file}"
    except OSError as e:
        return f"寫入檔案時發生錯誤: {e}"

# ==============================================================
# TOOL: 執行 Python 程式
# ==============================================================

@tool("run_python", args_schema=run_python_input)
def run_python(filename):
    """
    在工具可存取的根目錄下執行指定的 Python 腳本，並回傳 stdout 或 stderr 內容。

    Args:
        filename (str): 要執行的 Python 檔案相對路徑（相對於工具可存取的根目錄）。

    Returns:
        str: 執行成功時回傳 stdout；執行失敗時回傳 stderr；或發生例外則回傳例外說明。

    Security / Behavior:
        - 執行時會把工作目錄設為工具可存取的根目錄，避免腳本在其他路徑執行。
        - 不會在此處注入額外的環境變數或參數（簡潔、安全）。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    # 確保父資料夾存在（若不存在，subprocess 也會失敗；此處先建立以避免部分錯誤）
    os.makedirs(os.path.dirname(abs_file), exist_ok=True)

    try:
        # 使用系統 python 呼叫指定檔案，並在工具根目錄執行
        result = subprocess.run([
            "python", abs_file
        ], capture_output=True, text=True, cwd=abs_root)

        # 根據 returncode 回傳相對應內容（stdout 或 stderr）
        if result.returncode == 0:
            return result.stdout
        else:
            return result.stderr

    except Exception as e:
        # 以簡潔的錯誤格式回傳，方便 LLM 判讀
        return f"執行錯誤：{type(e).__name__} - {e}"

# ==============================================================
# TOOL: 讀取 PDF
# ==============================================================

@tool("read_pdf_file", args_schema=read_pdf_file_input)
def read_pdf_file(filename):
    """
    讀取 PDF 並將內容回傳為純文字。

    Args:
        filename (str): PDF 檔案相對路徑（相對於工具可存取的根目錄）。

    Returns:
        str: 合併後的純文字內容，或錯誤訊息字串。

    Error behavior:
        - 檔案不存在、權限不足或路徑安全檢查失敗時會回傳對應的錯誤訊息。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    try:
        loader = PyPDFLoader(abs_file)
        documents = loader.load()
        return document_to_txt(documents)
    except FileNotFoundError:
        return f"找不到檔案: {abs_file}"
    except PermissionError:
        return f"沒有權限讀取檔案: {abs_file}"

# ==============================================================
# TOOL: 讀取 Word (.docx)
# ==============================================================

@tool("read_docx_file", args_schema=read_docx_file_input)
def read_docx_file(filename):
    """
    讀取 .docx 文件，並回傳純文字內容。

    Args:
        filename (str): .docx 檔案相對路徑（相對於工具可存取的根目錄）。

    Returns:
        str: 合併後的純文字內容，或錯誤訊息字串。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    try:
        loader = UnstructuredWordDocumentLoader(abs_file)
        documents = loader.load()
        return document_to_txt(documents)
    except FileNotFoundError:
        return f"找不到檔案: {abs_file}"
    except PermissionError:
        return f"沒有權限讀取檔案: {abs_file}"

# ==============================================================
# TOOL: 讀取 Excel (.xlsx)
# ==============================================================

@tool("read_xlsx_file", args_schema=read_xlsx_file_input)
def read_xlsx_file(filename):
    """
    讀取 .xlsx 文件，並回傳純文字內容。

    Args:
        filename (str): .xlsx 檔案相對路徑（相對於工具可存取的根目錄）。

    Returns:
        str: 合併後的純文字內容，或錯誤訊息字串。
    """

    abs_file, abs_root = _abs_and_check(filename)

    if not abs_file.startswith(abs_root):
        return f"錯誤：不能存取超出根目錄的檔案！({filename})"

    try:
        loader = UnstructuredExcelLoader(abs_file)
        documents = loader.load()
        return document_to_txt(documents)
    except FileNotFoundError:
        return f"找不到檔案: {abs_file}"
    except PermissionError:
        return f"沒有權限讀取檔案: {abs_file}"

# End of file



from langchain_core.messages import ToolMessage, HumanMessage, SystemMessage, AIMessageChunk
from langchain_core.output_parsers import StrOutputParser

class stream_chat_bot:
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
            
            final_ai_message = AIMessageChunk(content="")
            for chunk in self.llm_with_tools.stream(self.message):
                final_ai_message += chunk
                if hasattr(chunk, 'content') and chunk.content:
                    yield self.str_parser.invoke(chunk)
            
            response = final_ai_message
            
            # 將 LLM 回應加入訊息列表
            self.message.append(response)

            # 檢查 LLM 是否要求呼叫工具
            is_tools_call = False
            for tool_call in response.tool_calls:
                is_tools_call = True

                # 顯示 LLM 要執行的工具名稱與參數
                # msg = f'【執行】: {tool_call["name"]}({tool_call["args"]})\n\n' #完整訊息
                msg = f'【執行】: {tool_call["name"]}()\n\n' #簡易訊息
                yield msg  # 使用 yield 讓結果能即時顯示在輸出中

                # 實際執行工具（根據工具名稱動態呼叫對應物件）
                tool_result = globals()[tool_call['name']].invoke(tool_call['args']) 

                # 顯示工具執行結果
                # msg = f'【結果】: {tool_result}\n\n'
                # yield msg

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
                # yield self.str_parser.invoke(response)
                return  # 結束對話流程

    def chat(self, text, print_output=False):
        """
        封裝版對話函式。
        會收集 chat_generator 的所有輸出，並組合成完整的回覆字串。
        """
        msg = ''
        # 逐步取得 chat_generator 的產出內容
        for chunk in self.chat_generator(text):
            msg += f"{chunk}"
            if print_output:
                print(chunk, end='')
        # 回傳最終組合的對話內容
        return msg

tools = [
    file_list,
    read_txt_file,
    save_txt_file,
    run_python,
    read_pdf_file,
    read_docx_file,
    read_xlsx_file,
]


import gradio as gr

# 建立 chat_bot 物件，並將 LLM 以及兩個工具（get_coordinates, get_weather）傳入
# 這樣 LLM 在回答時就能自動選擇使用這些工具
bot = stream_chat_bot(llm, tools)

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
demo = gr.ChatInterface(chat_function)

# 主程式進入點
# 啟動 Gradio Web 介面
if __name__ == "__main__":
    demo.launch()


