
from mcp.server.fastmcp import FastMCP
import sqlite3

mcp = FastMCP("mcp-db")

import sys

db_path = sys.argv[1]
@mcp.tool()
def sql_query(sql: str):
    """
    執行 SQL 查詢並回傳結果。
    資料表結構可以利用 get_schema() 工具獲取。
    
    Args:
        sql: 完整的 SQLite 查詢語句。
        
    Returns:
        str: 查詢結果字串，每列資料以換行分隔，欄位間以逗號分隔。
    """    
    try:
        if not sql.strip().upper().startswith("SELECT"):
            return "錯誤：僅允許執行 SELECT 查詢。"

        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        result_lines = [", ".join(map(str, row)) for row in rows]
        result_str = "\n".join(result_lines)
        conn.close()
        return result_str
    except sqlite3.Error as e:
        return f"SQL 執行錯誤: {e}"


@mcp.tool()
def get_schema():
    """
    獲取資料庫中所有資料表的 Schema 資訊，包含資料表名稱與欄位定義。
    在撰寫 SQL 查詢前，應先呼叫此工具以了解資料庫結構。
    
    Returns:
        str: 包含所有 CREATE TABLE 語句的字串。
    """
    try:    
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name;")
        schemas = cursor.fetchall()
        schema_text = "\n\n".join([row[0] for row in schemas if row[0] is not None])
        conn.close()
        return schema_text       
    except sqlite3.Error as e:
        return f"SQL 執行錯誤: {e}"



if __name__ == "__main__":
    mcp.run(transport='stdio')

