import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import pandas as pd
import json
import os
import requests
import re

# --- 1. 資料持久化設定 ---
FAVORITES_FILE = "favorites.json"


def load_favorites():
    if os.path.exists(FAVORITES_FILE):
        with open(FAVORITES_FILE, "r") as f:
            return json.load(f)
    return ["2330", "2317", "2603"]


def save_favorites(fav_list):
    with open(FAVORITES_FILE, "w") as f:
        json.dump(fav_list, f)


# 初始化狀態
if 'favorites' not in st.session_state:
    st.session_state['favorites'] = load_favorites()

if 'edit_mode' not in st.session_state:
    st.session_state['edit_mode'] = False

if 'fav_msg' not in st.session_state:
    st.session_state['fav_msg'] = ""

# 加入連動狀態：目前的分析目標與觸發器
if 'current_ticker' not in st.session_state:
    st.session_state['current_ticker'] = "2330"

if 'analyze_trigger' not in st.session_state:
    st.session_state['analyze_trigger'] = False

# --- 核心邏輯與函式 ---
st.set_page_config(page_title="全方位量化選股與預測系統", page_icon="📈", layout="wide")


def add_to_favorites():
    new_fav = st.session_state.fav_input.strip()
    if new_fav:
        if new_fav not in st.session_state['favorites']:
            st.session_state['favorites'].append(new_fav)
            save_favorites(st.session_state['favorites'])  # 存檔
            st.session_state.fav_msg = f"✅ 已成功加入 {new_fav}"
        else:
            st.session_state.fav_msg = "⚠️ 該股票已在清單中！"
    st.session_state.fav_input = ""


@st.cache_data(ttl=86400 * 7, show_spinner=False)
def build_tw_stock_mapping():
    mapping = {}
    headers = {"User-Agent": "Mozilla/5.0"}

    # 1. 抓取上市股票 (TWSE)
    try:
        res_twse = requests.get("https://openapi.twse.com.tw/v1/exchangeReport/STOCK_DAY_ALL", headers=headers,
                                timeout=5)
        if res_twse.status_code == 200:
            for item in res_twse.json():
                mapping[str(item.get("Code", ""))] = str(item.get("Name", ""))
    except:
        pass

    # 2. 抓取上櫃股票 (TPEx)
    try:
        # 呼叫櫃買中心的 OpenAPI
        res_tpex = requests.get("https://www.tpex.org.tw/openapi/v1/tpex_mainboard_quotes", headers=headers, timeout=5)
        if res_tpex.status_code == 200:
            for item in res_tpex.json():
                code = str(item.get("SecuritiesCompanyCode", "")).strip()
                name = str(item.get("CompanyName", "")).strip()
                if code:
                    mapping[code] = name
    except:
        pass

    return mapping


def get_stock_name(ticker_str):
    clean_ticker = str(ticker_str).strip().upper().replace('.TW', '').replace('.TWO', '')
    mapping = build_tw_stock_mapping()
    name = mapping.get(clean_ticker)
    if name and name != clean_ticker:
        return f"{clean_ticker} {name}"
    return clean_ticker


# --- 側邊欄 ---
with st.sidebar:
    st.header("⭐ 我的最愛管理")
    st.text_input("新增股票代碼 (台股)", key="fav_input", on_change=add_to_favorites)

    if st.session_state.fav_msg:
        st.info(st.session_state.fav_msg)
        st.session_state.fav_msg = ""

    st.divider()
    col_title, col_btn = st.columns([4, 1])
    with col_title:
        st.subheader("📋 目前觀察清單")
    with col_btn:
        if st.button("⋮"):
            st.session_state['edit_mode'] = not st.session_state['edit_mode']
            st.rerun()

    for fav in st.session_state['favorites']:
        if st.session_state['edit_mode']:
            c1, c2 = st.columns([3, 1])
            c1.write(f"**{fav}**")
            if c2.button("❌", key=f"del_{fav}"):
                st.session_state['favorites'].remove(fav)
                save_favorites(st.session_state['favorites'])  # 存檔
                st.rerun()
        else:
            # 將清單改成按鈕，點擊後會連動主畫面的輸入框並觸發分析
            if st.button(f"🔍 {get_stock_name(fav)}", key=f"view_{fav}", use_container_width=True):
                st.session_state['current_ticker'] = fav
                st.session_state['analyze_trigger'] = True

# ==========================================
# 內建主題股票池
# ==========================================
STOCK_POOLS = {
    "⭐ 我的最愛清單": st.session_state['favorites'],
    "🏆 台灣大型權值": ["2330", "2317", "2454", "2308", "2881", "2891", "2603"],
    "🤖 AI 伺服器與散熱": ["2382", "3231", "2376", "3324", "3017", "3362", "2356"],
    "⚡ 半導體設備與矽光子": ["3131", "3450", "3583", "3374", "3163", "6187", "3443"],
    "🚢 航運與重電": ["2603", "2609", "2615", "1519", "1503", "1513"],
    "📈 高股息 ETF": ["0050", "0056", "00878", "00929", "00919"]
}


# --- 3. 核心邏輯：資料獲取與特徵工程 ---
@st.cache_data(ttl=3600)
def load_and_analyze_data(ticker, period="1y"):
    ticker = str(ticker).strip().upper()
    if ticker.isdigit():
        df = yf.download(f"{ticker}.TW", period=period)
        if df.empty:
            df = yf.download(f"{ticker}.TWO", period=period)
    else:
        df = yf.download(ticker, period=period)

    if df is None or df.empty:
        return None

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df['MA20'] = df['Close'].rolling(window=20).mean()
    df['MA60'] = df['Close'].rolling(window=60).mean()

    df['Signal'] = 0
    df.loc[(df['MA20'] > df['MA60']) & (df['MA20'].shift(1) <= df['MA60'].shift(1)), 'Signal'] = 1
    df.loc[(df['MA20'] < df['MA60']) & (df['MA20'].shift(1) >= df['MA60'].shift(1)), 'Signal'] = -1

    df['Rolling_Max'] = df['High'].rolling(window=20).max()
    df['Trailing_Stop_Price'] = df['Rolling_Max'] * 0.93
    condition_uptrend = df['MA20'] > df['MA60']
    condition_drop_below_ts = (df['Close'] < df['Trailing_Stop_Price']) & (
            df['Close'].shift(1) >= df['Trailing_Stop_Price'].shift(1))
    df.loc[condition_uptrend & condition_drop_below_ts, 'Signal'] = -2

    df['Vol_MA5'] = df['Volume'].rolling(window=5).mean()
    df['Vol_Ratio'] = df['Volume'] / df['Vol_MA5']
    df['STD20'] = df['Close'].rolling(window=20).std()
    df['Upper_BB'] = df['MA20'] + (df['STD20'] * 2)
    df['Lower_BB'] = df['MA20'] - (df['STD20'] * 2)
    df['BB_Width'] = (df['Upper_BB'] - df['Lower_BB']) / df['MA20']

    df['Prediction_Signal'] = 0
    condition_volume = df['Vol_Ratio'] >= 2.0
    condition_breakout = df['Close'] > df['Upper_BB']
    condition_squeeze = df['BB_Width'].shift(1) < df['BB_Width'].rolling(60).quantile(0.2)
    df.loc[condition_volume & condition_breakout & condition_squeeze, 'Prediction_Signal'] = 1

    return df


# --- 4. UI 介面設計 ---
st.title("📈 股市量化分析與異動預測系統")

tab1, tab2, tab3, tab4 = st.tabs([
    "📊 個股深度分析",
    "🔮 短線爆發預測雷達",
    "🎯 趨勢掃描選股",
    "🔔 賣出/停損診斷"
])

# ==========================================
# 分頁 1：個股深度分析
# ==========================================
with tab1:
    st.markdown("輸入股票代碼，或從左側邊欄點擊「我的最愛」標的即可直接分析。")
    col1, col2 = st.columns([2, 1])
    with col1:
        # 將輸入框直接綁定 current_ticker
        ticker = st.text_input("輸入股票代碼", key="current_ticker")
    with col2:
        period = st.selectbox("時間範圍", ["6mo", "1y", "2y"], index=1)

    analyze_clicked = st.button("開始分析", use_container_width=True, key="btn1")

    # 如果手動點擊，或側邊欄觸發了分析
    if analyze_clicked or st.session_state['analyze_trigger']:
        st.session_state['analyze_trigger'] = False  # 重置觸發器避免重複執行

        if not ticker.strip():
            st.warning("請輸入股票代碼！")
        else:
            with st.spinner("計算數據中..."):
                df = load_and_analyze_data(ticker, period)
                if df is None or df.empty:
                    st.error("找不到該股票資料，請確認代碼是否正確。")
                else:
                    stock_name = get_stock_name(ticker)
                    st.markdown(f"### 📊 {stock_name}")

                    latest_close = float(df['Close'].iloc[-1])
                    prev_close = float(df['Close'].iloc[-2])
                    change = latest_close - prev_close
                    change_pct = (change / prev_close) * 100
                    ma20_val = float(df['MA20'].iloc[-1])
                    ma60_val = float(df['MA60'].iloc[-1])

                    m1, m2, m3 = st.columns(3)
                    m1.metric("最新收盤價", f"{latest_close:.2f}", f"{change:.2f} ({change_pct:.2f}%)")
                    m2.metric("MA20 (月線)", f"{ma20_val:.2f}")
                    m3.metric("MA60 (季線)", f"{ma60_val:.2f}")

                    st.divider()
                    st.subheader("💡 系統自動數據解讀")
                    if latest_close > ma20_val > ma60_val:
                        st.success(f"**強勢多頭：** 站上月季線。建議持股續抱，拉回月線不破可加碼。")
                    elif ma20_val > latest_close > ma60_val:
                        st.warning(f"**高檔震盪：** 跌破月線。短線轉弱，跌破季線需考慮減碼。")
                    elif ma60_val > ma20_val > latest_close:
                        st.error(f"**弱勢空頭：** 跌破所有均線。建議空手觀望，切勿輕易摸底。")
                    else:
                        st.info(f"**盤整區間：** 均線糾結。建議縮小部位，等待明確突破。")
                    st.divider()

                    # 建立圖表
                    fig = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.03,
                                        row_heights=[0.7, 0.3])

                    # 1. K線與均線
                    fig.add_trace(
                        go.Candlestick(x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
                                       name="K線", increasing_line_color='red', decreasing_line_color='green'), row=1,
                        col=1)
                    fig.add_trace(
                        go.Scatter(x=df.index, y=df['MA20'], line=dict(color='orange', width=1.5), name="MA20"),
                        row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['MA60'], line=dict(color='blue', width=1.5), name="MA60"),
                                  row=1, col=1)

                    # 2. 布林通道與移動停利線
                    fig.add_trace(go.Scatter(x=df.index, y=df['Upper_BB'],
                                             line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dash'),
                                             name="布林上軌"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['Lower_BB'],
                                             line=dict(color='rgba(150, 150, 150, 0.4)', width=1, dash='dash'),
                                             name="布林下軌"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=df.index, y=df['Trailing_Stop_Price'],
                                             line=dict(color='rgba(128, 0, 128, 0.4)', width=1.5, dash='dot'),
                                             name="移動停利線"), row=1, col=1)

                    # 3. 訊號標記
                    buy_signals = df[df['Signal'] == 1]
                    sell_signals = df[df['Signal'] == -1]
                    take_profit_signals = df[df['Signal'] == -2]
                    pred_signals = df[df['Prediction_Signal'] == 1]

                    fig.add_trace(go.Scatter(x=buy_signals.index, y=buy_signals['Low'] * 0.95, mode='markers',
                                             marker=dict(symbol='triangle-up', color='red', size=12), name="買進訊號"),
                                  row=1, col=1)
                    fig.add_trace(go.Scatter(x=sell_signals.index, y=sell_signals['High'] * 1.05, mode='markers',
                                             marker=dict(symbol='triangle-down', color='green', size=12),
                                             name="賣出訊號"),
                                  row=1, col=1)
                    fig.add_trace(
                        go.Scatter(x=take_profit_signals.index, y=take_profit_signals['High'] * 1.05, mode='markers',
                                   marker=dict(symbol='diamond', color='purple', size=14,
                                               line=dict(width=1, color='white')), name="獲利了結"), row=1, col=1)
                    fig.add_trace(go.Scatter(x=pred_signals.index, y=pred_signals['Low'] * 0.92, mode='markers',
                                             marker=dict(symbol='star', color='gold', size=16,
                                                         line=dict(width=1, color='black')), name="潛力爆發"), row=1,
                                  col=1)

                    # 4. 成交量與均量
                    colors = ['red' if row['Close'] >= row['Open'] else 'green' for i, row in df.iterrows()]
                    fig.add_trace(go.Bar(x=df.index, y=df['Volume'], marker_color=colors, name="成交量"), row=2, col=1)
                    fig.add_trace(
                        go.Scatter(x=df.index, y=df['Vol_MA5'], line=dict(color='orange', width=1.5), name="5日均量"),
                        row=2, col=1)

                    fig.update_layout(
                        xaxis_rangeslider_visible=False,
                        height=700,
                        margin=dict(l=0, r=0, t=10, b=0),
                        legend=dict(
                            orientation="h",
                            yanchor="top", y=-0.1,
                            xanchor="center", x=0.5,
                        )
                    )
                    st.plotly_chart(fig, use_container_width=True)

# ==========================================
# 分頁 2：短線爆發預測雷達
# ==========================================
with tab2:
    st.subheader("異動爆發預測雷達")
    selected_pool_2 = st.selectbox("選擇要掃描的板塊 / 股票池", list(STOCK_POOLS.keys()), key="pool_2")

    if st.button("啟動預測掃描", type="primary", key="btn2"):
        target_stocks = STOCK_POOLS[selected_pool_2]
        if not target_stocks:
            st.warning("該清單目前為空，請先至側邊欄新增股票。")
        else:
            progress_bar = st.progress(0)
            predictions = []

            for i, stock in enumerate(target_stocks):
                df_scan = load_and_analyze_data(stock, "3mo")
                if df_scan is not None and not df_scan.empty:
                    latest = df_scan.iloc[-1]
                    if latest['Prediction_Signal'] == 1:
                        status = "強烈爆發預警"
                    elif latest['Vol_Ratio'] > 2.5:
                        status = f"異常爆量 ({latest['Vol_Ratio']:.1f} 倍)"
                    else:
                        status = "正常波動"

                    if status != "正常波動":
                        stock_name = get_stock_name(stock)
                        predictions.append(
                            {"股票代碼": stock, "名稱": stock_name, "最新收盤價": f"{latest['Close']:.2f}",
                             "狀態": status})
                progress_bar.progress((i + 1) / len(target_stocks))
            progress_bar.empty()

            if predictions:
                st.success(f"掃描完成！發現異常波動標的：")
                st.table(pd.DataFrame(predictions))
            else:
                st.info("尚未偵測到明顯的爆發訊號。")

# ==========================================
# 分頁 3：趨勢掃描選股
# ==========================================
with tab3:
    st.subheader("趨勢多頭掃描")
    selected_pool_3 = st.selectbox("選擇要掃描的板塊 / 股票池", list(STOCK_POOLS.keys()), key="pool_3")

    if st.button("開始掃描多頭股", use_container_width=True, key="btn3"):
        target_stocks = STOCK_POOLS[selected_pool_3]
        if not target_stocks:
            st.warning("該清單目前為空，請先至側邊欄新增股票。")
        else:
            my_bar = st.progress(0)
            buy_list = []

            for i, stock in enumerate(target_stocks):
                df_scan = load_and_analyze_data(stock, "6mo")
                if df_scan is not None and not df_scan.empty:
                    latest = df_scan.iloc[-1]
                    if latest['Signal'] == 1 or (latest['Close'] > latest['MA20'] and latest['MA20'] > latest['MA60']):
                        buy_list.append((stock, latest['Close']))
                my_bar.progress((i + 1) / len(target_stocks))
            my_bar.empty()

            if buy_list:
                st.success("以下標的目前呈現偏多趨勢：")
                for item in buy_list:
                    stock_name = get_stock_name(item[0])
                    st.write(f"- **{stock_name}** (最新收盤價: {item[1]:.2f})")
            else:
                st.info("沒有符合條件的標的。")

# ==========================================
# 分頁 4：持股賣出與停損診斷
# ==========================================
with tab4:
    st.subheader("庫存健康度診斷")
    c1, c2 = st.columns(2)
    with c1:
        def format_dropdown_tab4(t):
            if t == "自訂輸入...": return t
            name = get_stock_name(t)
            return name if name else t


        hold_ticker = st.selectbox(
            "選擇持股",
            options=st.session_state['favorites'] + ["自訂輸入..."],
            key="tab4_ticker",
            format_func=format_dropdown_tab4
        )
        if hold_ticker == "自訂輸入...":
            hold_ticker = st.text_input("請輸入自訂代碼", key="tab4_custom")
    with c2:
        cost_price = st.number_input("買進成本價", min_value=0.0, value=0.0, step=1.0)

    stop_loss_pct = st.slider("設定停損幅度 (%)", min_value=-30, max_value=-5, value=-10)

    if st.button("執行診斷", use_container_width=True, type="primary", key="btn4"):
        if hold_ticker and cost_price > 0:
            df_hold = load_and_analyze_data(hold_ticker, "6mo")
            if df_hold is not None and not df_hold.empty:
                latest_close = float(df_hold['Close'].iloc[-1])
                trailing_stop_val = float(df_hold['Trailing_Stop_Price'].iloc[-1])
                roi_pct = ((latest_close - cost_price) / cost_price) * 100

                st.divider()
                stock_name = get_stock_name(hold_ticker)
                st.write(
                    f"診斷標的: **{stock_name}** | 當前市價: **{latest_close:.2f}** | 你的成本: **{cost_price:.2f}**")
                color = "red" if roi_pct >= 0 else "green"
                st.markdown(
                    f"未實現損益: <span style='color:{color}; font-size:24px; font-weight:bold;'>{roi_pct:.2f}%</span>",
                    unsafe_html=True)

                if roi_pct <= stop_loss_pct:
                    st.error(f"【強烈建議賣出】已觸發停損機制！")
                elif latest_close < trailing_stop_val and roi_pct > 0:
                    st.warning(f"【提早獲利了結】跌破移動停利線！建議先獲利入袋。")
                else:
                    st.success("【持股續抱】技術面健康，未觸碰停損與停利線！")