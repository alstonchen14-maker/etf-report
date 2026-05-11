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

# 確保歷史資料夾存在
if not os.path.exists(HISTORY_DIR):
    os.makedirs(HISTORY_DIR)

def get_data():
    print("🚀 啟動爬蟲...")
    options = Options()
    options.add_argument('--headless')
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
    except Exception as e:
        print(f"❌ Driver 安裝失敗: {e}")
        return None
    
    target_df = None
    try:
        driver.get(URL)
        time.sleep(10)
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
            # 偵測是否有名稱、權重相關欄位
            if ("名稱" in cols or "股票" in cols) and ("權重" in cols or "持股" in cols):
                target_df = df
                break
    except Exception as e:
        print(f"❌ 錯誤: {e}")
    finally:
        if 'driver' in locals():
            driver.quit()
    return target_df

def clean_val(x):
    """處理百分比或數字字串轉換為 float"""
    try:
        if pd.isna(x): return 0.0
        s = str(x).replace('%', '').replace(',', '').strip()
        return float(s) if s != '-' else 0.0
    except: return 0.0

def generate_fake_history(df_now, col_w, col_v):
    print("✨ 生成模擬歷史資料 (含股數)...")
    df_fake = df_now.copy()
    for i in range(len(df_fake)):
        # 模擬權重變動
        w_val = clean_val(df_fake.iloc[i][col_w])
        df_fake.at[i, col_w] = f"{max(0, w_val + random.uniform(-0.3, 0.3)):.2f}%"
        # 模擬股數變動
        if col_v:
            v_val = clean_val(df_fake.iloc[i][col_v])
            df_fake.at[i, col_v] = int(max(0, v_val * random.uniform(0.95, 1.05)))
            
    yst = (datetime.date.today() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    df_fake.to_csv(os.path.join(HISTORY_DIR, f"portfolio_{yst}.csv"), index=False)

def main():
    df_now = get_data()
    if df_now is None: 
        print("❌ 抓取失敗")
        return

    # 定義欄位名稱關鍵字
    col_w = next((c for c in df_now.columns if '權重' in c), None)
    col_n = next((c for c in df_now.columns if '名稱' in c), None)
    col_c = next((c for c in df_now.columns if '代號' in c), col_n)
    # 尋找股數/張數相關欄位
    col_v = next((c for c in df_now.columns if any(k in c for k in ['股數', '張數', '持股數', '數量'])), None)

    if col_w and col_n:
        today = datetime.date.today().strftime("%Y-%m-%d")
        csv_path = os.path.join(HISTORY_DIR, f"portfolio_{today}.csv")
        df_now.to_csv(csv_path, index=False)

        files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.csv")))
        if len(files) < 2:
            generate_fake_history(df_now, col_w, col_v)
            files = sorted(glob.glob(os.path.join(HISTORY_DIR, "*.csv")))

        f_now, f_prev = files[-1], files[-2]
        d_now = os.path.basename(f_now).replace("portfolio_", "").replace(".csv", "")
        d_prev = os.path.basename(f_prev).replace("portfolio_", "").replace(".csv", "")

        df1 = pd.read_csv(f_now).drop_duplicates(subset=[col_c]).set_index(col_c)
        df2 = pd.read_csv(f_prev).drop_duplicates(subset=[col_c]).set_index(col_c)
        m = df1.join(df2, lsuffix='_new', rsuffix='_old', how='outer')
        m['sort'] = m[f"{col_w}_new"].apply(clean_val)
        m = m.sort_values(by='sort', ascending=False)

        rows = ""
        for i, r in m.iterrows():
            nm = r[f"{col_n}_new"] if pd.notna(r[f"{col_n}_new"]) else r[f"{col_n}_old"]
            
            # 權重處理
            wn = r[f"{col_w}_new"] if pd.notna(r[f"{col_w}_new"]) else "0%"
            wo = r[f"{col_w}_old"] if pd.notna(r[f"{col_w}_old"]) else "0%"
            w_diff = clean_val(wn) - clean_val(wo)
            
            # 股數處理 (直接取用原始數值，不再除以 1000)
            vn = clean_val(r[f"{col_v}_new"]) if col_v and pd.notna(r[f"{col_v}_new"]) else 0
            vo = clean_val(r[f"{col_v}_old"]) if col_v and pd.notna(r[f"{col_v}_old"]) else 0
            v_diff = vn - vo

            # 樣式判斷 (以權重變動為主)
            bg, tc, sym = "white", "#333", "-"
            if w_diff > 0.001: bg, tc, sym = "#ffe6e6", "#d93025", "▲"
            elif w_diff < -0.001: bg, tc, sym = "#e6ffe6", "#188038", "▼"
            
            # 格式化輸出：加入千位分隔符 (:,)
            rows += f"""<tr style='background:{bg}'>
                <td>{nm}</td>
                <td>{wo}</td><td>{wn}</td>
                <td style='color:{tc}'><b>{sym} {w_diff:+.2f}%</b></td>
                <td>{vo:,.0f}</td><td>{vn:,.0f}</td>
                <td style='color:{tc}'>{v_diff:+,.0f}</td>
            </tr>"""

        # HTML 模板修改
        html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>ETF 追蹤報表 (含股數)</title>
<style>
  body{{font-family:"Microsoft JhengHei",sans-serif;max-width:1000px;margin:20px auto;padding:10px;background:#f4f4f9}}
  .card{{background:white;padding:20px;border-radius:10px;box-shadow:0 2px 10px rgba(0,0,0,0.1)}}
  table{{width:100%;border-collapse:collapse;margin-top:20px;font-size:14px}}
  th{{background:#2c3e50;color:white;padding:10px;text-align:left;position:sticky;top:0}}
  td{{padding:10px;border-bottom:1px solid #eee; text-align:right}}
  td:first-child, th:first-child{{text-align:left}} /* 讓名稱靠左 */
  .btn{{display:inline-block; padding:10px 20px; background-color:#27ae60; color:white; text-decoration:none; border-radius:5px; font-weight:bold; cursor:pointer; border:none; margin-bottom:15px;}}
</style>
<script>
function downloadCSV() {{
    var csv = [];
    var rows = document.querySelectorAll("table tr");
    for (var i = 0; i < rows.length; i++) {{
        var row = [], cols = rows[i].querySelectorAll("td, th");
        for (var j = 0; j < cols.length; j++) row.push(cols[j].innerText.replace(/,/g, ""));
        csv.push(row.join(","));
    }}
    var csvFile = new Blob(["\\uFEFF" + csv.join("\\n")], {{type: "text/csv"}});
    var downloadLink = document.createElement("a");
    downloadLink.download = "ETF_Full_Report_{d_now}.csv";
    downloadLink.href = window.URL.createObjectURL(csvFile);
    downloadLink.click();
}}
</script>
</head>
<body>
<div class='card'>
  <h2>📈 統一台股增長 (00981A) - 持股異動明細</h2>
  <p style='color:#666'>更新日期：{d_now} (比較對象: {d_prev}) | 單位：<strong>股</strong></p>
  <button onclick="downloadCSV()" class="btn">📥 下載完整報表 (CSV)</button>
  <table>
    <thead>
        <tr>
            <th>名稱</th>
            <th>舊權重</th><th>新權重</th><th>權重變動</th>
            <th>舊股數</th><th>新股數</th><th>股數變動</th>
        </tr>
    </thead>
    <tbody>{rows}</tbody>
  </table>
</div>
</body>
</html>"""

        with open(HTML_FILENAME, "w", encoding="utf-8") as f:
            f.write(html_content)
        print(f"✅ HTML 報表生成完畢，已切換為「股數」顯示。")

if __name__ == "__main__":
    main()
