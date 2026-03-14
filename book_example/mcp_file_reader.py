from mcp.server.fastmcp import FastMCP

# 建立 MCP Server，名稱可自訂
mcp = FastMCP("file-reader")

# 定義一個簡單的工具
@mcp.tool()
def read_file(path: str) -> str:
    """讀取文字檔案內容"""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()

# 啟動 MCP 伺服器（使用 stdio 模式）
if __name__ == "__main__":
    mcp.run(transport='stdio')
