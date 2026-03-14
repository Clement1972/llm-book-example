
import pandas as pd

try:
    df = pd.read_csv("heart.csv")
    correlations = df.corr()['target'].sort_values(ascending=False)
    print("與心臟病 (target) 欄位相關性最高的欄位：")
    print(correlations)
except FileNotFoundError:
    print("錯誤：heart.csv 檔案未找到。")
except Exception as e:
    print(f"處理檔案時發生錯誤: {e}")
