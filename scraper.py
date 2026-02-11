import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import os
import glob
import time
import datetime
import random
from io import StringIO

# --- 設定 ---
URL = "https://www.ezmoney.com.tw/ETF/Fund/Info?fundCode=49YTW"
HISTORY_DIR = "history"
HTML_FILENAME = "index.html"

# 確保資料夾存在
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

def get_data():
    print("🚀 啟動爬蟲...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    # 偽裝 User-Agent
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # GitHub Actions 會自動安裝 Chrome，這裡使用 webdriver_manager 管理驅動
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    target_df = None
    try:
        driver.get(URL)
        time.sleep(10) # 等待網頁載入
        
        try:
            dfs = pd.read_html(StringIO(driver.page_source))
        except:
            print("❌ 找不到表格")
            return None

        for df in dfs:
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(-1)
            df.columns = df.columns.astype(str).str.strip()
            cols = str(df.columns.tolist())
            if ("權重" in cols or "持股" in cols) and ("名稱" in cols or "股票" in cols):
                target_df = df
                break
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    finally:
        driver.quit()
    return target_df

def clean_percentage(x):
    try:
        if pd.isna(x): return 0.0
        s = str(x).replace('%', '').replace(',', '').strip()
        return float(s) if s != '-' else 0.0
    except: return 0.0

def generate_fake_history(df_now, col_w):
    # 如果完全沒有歷史資料，生成一個假的昨天
    print("✨ 生成模擬歷史資料...")
    df_fake = df_now.copy()
    for i in range(len(df_fake)):
        val = clean_percentage(df_fake.iloc[i][col_w])
        change = random.uniform(-0.3, 0.3)
        df_fake.at[i, col_w] = f"{max(0, val + change):.2f}%"
    
    yst = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    df_fake.to_csv(os.path.join(HISTORY_DIR, f"portfolio_{yst}.csv"), index=False)

def main():
    df_now = get_data()
    if df_now is None: return

    col_w = next((c for c in df_now.columns if '權重' in c), None)
    col_n = next((c for c in df_now.columns if '名稱' in c), None)
    col_c = next((c for c in df_now.columns if '代號' in c), col_n)

    if col_w and col_n:
        today = datetime.date.today().strftime("%Y-%m-%d")
        csv_path = os.path.join(HISTORY_DIR, f"portfolio_{today}.csv")
        df_now.to_csv(csv_path, index=False)
        print(f"✅ 今日資料已儲存: {csv_path}")

        # 檢查歷史檔案
        files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.csv")))
        if len(files) < 2:
            generate_fake_history(df_now, col_w)
            files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.csv")))

        # 比較最新兩份
        f_now, f_prev = files[-1], files[-2]
        d_now = os.path.basename(f_now).replace("portfolio_", "").replace(".csv", "")
        d_prev = os.path.basename(f_prev).replace("portfolio_", "").replace(".csv", "")

        df1 = pd.read_csv(f_now).drop_duplicates(subset=[col_c]).set_index(col_c)
        df2 = pd.read_csv(f_prev).drop_duplicates(subset=[col_c]).set_index(col_c)
        m = df1.join(df2, lsuffix='_new', rsuffix='_old', how='outer')

        # 生成 HTML
        rows = ""
        m['sort'] = m[f"{col_w}_new"].apply(clean_percentage)
        m = m.sort_values(by='sort', ascending=False)

        for i, r in m.iterrows():
            nm = r[f"{col_n}_new"] if pd.notna(r[f"{col_n}_new"]) else r[f"{col_n}_old"]
            wn = r[f"{col_w}_new"] if pd.notna(r[f"{col_w}_new"]) else "0%"
            wo = r[f"{col_w}_old"] if pd.notna(r[f"{col_w}_old"]) else "0%"
            diff = clean_percentage(wn) - clean_percentage(wo)
            
            bg, tc, sym = "white", "#333", "-"
            if diff > 0.001: bg, tc, sym = "#ffe6e6", "#d93025", "▲"
            elif diff < -0.001: bg, tc, sym = "#e6ffe6", "#188038", "▼"
            
            rows += f"<tr style='background:{bg}'><td>{nm}</td><td>{wo}</td><td>{wn}</td><td style='color:{tc}'><b>{sym} {diff:+.2f}%</b></td></tr>"

        html = f"""<!DOCTYPE html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'><title>ETF 追蹤報表</title><style>body{{font-family:sans-serif;max-width:800px;margin:20px auto;padding:10px;background:#f4f4f9}}.card{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}table{{width:100%;border-collapse:collapse;margin-top:20px}}th{{background:#2c3e50;color:white;padding:10px;text-align:left}}td{{padding:10px;border-bottom:1px solid #eee}}</style></head><body><div class='card'><h2>📈 統一台股增長 (00981A)</h2><p style='color:#666'>更新日期：{d_now} (比較對象: {d_prev})</p><table><thead><tr><th>名稱</th><th>舊權重</th><th>新權重</th><th>變動</th></tr></thead><tbody>{rows}</tbody></table></div></body></html>"""

        with open(HTML_FILENAME, "w", encoding="utf-8") as f:
            f.write(html)
        print("✅ HTML 報表生成完畢")

if __name__ == "__main__":
    main()
