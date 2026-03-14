
from mcp.server.fastmcp import FastMCP

# 建立 MCP Server，名稱可自訂
mcp = FastMCP("weather")

# 匯入 geopy 套件中的 Nominatim 類別，用於地理編碼（將地名轉換成經緯度）
from geopy.geocoders import Nominatim, ArcGIS

# 定義函式：輸入城市名稱，回傳其經緯度座標
@mcp.tool()
def get_coordinates(city_name: str) -> tuple[float, float] | None:
    """
    根據城市名稱取得該城市的緯度和經度。

    Args:
        city_name (str): 欲查詢的城市名稱。

    Returns:
        tuple[float, float] | None: 如果找到城市，則返回包含緯度和經度的元組；
                                   否則返回 None。
    """
    # ---- 第一來源：Nominatim ----
    try:
        geolocator1 = Nominatim(user_agent="clement_fallback_test")
        location = geolocator1.geocode(city_name, timeout=10)

        if location:
            return (location.latitude, location.longitude)
    except:
        pass  # 忽略錯誤，直接進入第二來源

    # ---- 第二來源：ArcGIS  ----
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
@mcp.tool()
def get_weather(latitude: float, longitude: float) -> float:
    """
    根據緯度和經度獲取當前溫度。

    Args:
        latitude (float): 欲查詢地點的緯度。
        longitude (float): 欲查詢地點的經度。

    Returns:
        float: 該地點的當前溫度（攝氏）。
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

# 啟動 MCP 伺服器（使用 stdio 模式）
if __name__ == "__main__":
    mcp.run(transport='stdio')
