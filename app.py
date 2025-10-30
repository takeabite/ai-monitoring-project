# app.py
import streamlit as st
import pandas as pd, time, os, json
from config import LOG_FILE
from datetime import datetime
from streamlit_autorefresh import st_autorefresh
from collections import Counter, defaultdict
import plotly.express as px

st.set_page_config(page_title="Real-time TX Monitor", layout="wide")
st.title("📈 AI 기반 실시간 거래 모니터링")

# auto refresh every 3 seconds
count = st_autorefresh(interval=3000, limit=None, key="autorefresh")

st.sidebar.header("Settings")
n_recent = st.sidebar.slider("최근표시건수", 50, 1000, 200)

ANOMALY_FILE = LOG_FILE + ".anomalies.jsonl"

def read_log(limit_lines=5000):
    if not os.path.exists(LOG_FILE):
        return pd.DataFrame()
    with open(LOG_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()[-limit_lines:]
    import re
    pattern = re.compile(
        r"\[(?P<ts>[^\]]+)\]\s+status=(?P<status>\w+)\s+latency=(?P<lat>[\d\.]+)ms\s+merchant=(?P<merchant>\S+)\s+region=(?P<region>\S+)\s+amount=(?P<amount>[\d\.]+)"
    )
    rows=[]
    for L in lines:
        m = pattern.search(L)
        if m:
            d = m.groupdict()
            rows.append({
                "timestamp": pd.to_datetime(d["ts"]),
                "status": 1 if d["status"]=="SUCCESS" else 0,
                "latency": float(d["lat"]),
                "merchant": d["merchant"],
                "region": d["region"],
                "amount": float(d["amount"]),
                "raw": L.strip()
            })
    if not rows:
        return pd.DataFrame()
    df = pd.DataFrame(rows)
    df = df.sort_values("timestamp").tail(n_recent)
    return df

def read_anomalies(limit=1000):
    items = []
    if not os.path.exists(ANOMALY_FILE):
        return pd.DataFrame()
    with open(ANOMALY_FILE, "r", encoding="utf-8") as f:
        for l in f.readlines()[-limit:]:
            try:
                items.append(json.loads(l))
            except:
                continue
    if not items:
        return pd.DataFrame()
    df = pd.DataFrame(items)
    # normalize datetime
    if "detected_at" in df.columns:
        df["detected_at"] = pd.to_datetime(df["detected_at"])
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df

df = read_log()
an_df = read_anomalies(1000)

col1, col2, col3 = st.columns([1,1,1])
with col1:
    st.metric("총 거래(표시)", len(df))
with col2:
    if not df.empty:
        st.metric("최근 평균 지연(ms)", f"{df['latency'].mean():.1f}")
    else:
        st.metric("최근 평균 지연(ms)", "-")
with col3:
    if not df.empty:
        reject_rate = 100*(1 - df['status'].mean())
        st.metric("최근 거절율(%)", f"{reject_rate:.2f}")
    else:
        st.metric("최근 거절율(%)", "-")

# --- 이상 타입 한글 매핑 ---
TYPE_KO = {
    "autoencoder": "AI 이상(AutoEncoder)",
    "high_latency": "고지연",
    "high_amount": "고액",
    "unknown_merchant": "미등록 상점",
    "unknown_region": "미등록 지역",
    "failure": "거래 실패",
    "off_hour": "심야 거래",
    "burst": "버스트",
    "card_testing": "카드 테스트(소액 반복)",
    "merchant_spike": "상점 폭주",
    "composite": "복합 이상"
}

def types_to_ko_list(types):
    if isinstance(types, list):
        return [TYPE_KO.get(t, t) for t in types]
    # try to parse string representation like "['a','b']"
    try:
        parsed = eval(types)
        if isinstance(parsed, list):
            return [TYPE_KO.get(t, t) for t in parsed]
    except:
        pass
    return []

# anomaly summary
st.subheader("이상 이벤트 요약")
if an_df.empty:
    st.write("감지된 이상 이벤트가 없습니다.")
else:
    # add a column with Korean labels for display (keeps existing column for table)
    an_df["types_ko"] = an_df["types"].apply(types_to_ko_list)

    # 필터링: UI에서 제외할 이상 타입 (원문 키)
    SKIP_TYPES = {"merchant_spike", "off_hour", "unknown_region"}

    # flatten and count using 원문 keys -> 한글 라벨 매핑, 제외 타입는 건너뜀
    type_counts = Counter()
    for raw in an_df["types"].tolist():
        keys = []
        if raw is None:
            continue
        if isinstance(raw, list):
            keys = raw
        elif isinstance(raw, str):
            # JSON으로 저장된 경우 우선 파싱, 실패하면 eval로 시도
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    keys = parsed
            except Exception:
                try:
                    parsed = eval(raw)
                    if isinstance(parsed, list):
                        keys = parsed
                except Exception:
                    keys = []
        else:
            keys = []
        for k in keys:
            if k in SKIP_TYPES:
                continue
            type_counts[ TYPE_KO.get(k, k) ] += 1
    tc_df = pd.DataFrame(type_counts.items(), columns=["type","count"]).sort_values("count", ascending=False)

    # horizontal bar: 글자 크기 키움
    if not tc_df.empty:
        fig = px.bar(tc_df, x="type", y="count", text="count")
        fig.update_traces(textposition="outside", textfont=dict(size=12))
        fig.update_layout(
            font=dict(size=16), 
            margin=dict(l=20, r=20, t=30, b=40),
            height=420,
            bargap=0.2
        )
        fig.update_xaxes(tickfont=dict(size=14), title_text="")
        fig.update_yaxes(tickfont=dict(size=14), title_text="건수")

        st.plotly_chart(fig, use_container_width=True)
    else:
        st.write("이상 유형 데이터가 없습니다.")

    # time series: anomalies per minute
    ts = an_df.copy()
    if "detected_at" in ts.columns and not ts["detected_at"].isna().all():
        ts["minute"] = ts["detected_at"].dt.floor("min")
        per_min = ts.groupby("minute").size().rename("count").reset_index()
        if not per_min.empty:
            st.line_chart(per_min.set_index("minute")["count"])

    st.subheader("최근 이상 목록 (최신 100)")
    disp = an_df.sort_values("detected_at", ascending=False).head(100)
    if not disp.empty:
        # 보여줄 때 한국어 타입 컬럼도 함께 표시
        disp_display = disp[["detected_at","types","types_ko","merchant","region","amount","latency","err","raw"]].reset_index(drop=True)
        st.dataframe(disp_display)

st.subheader("Latency 추세 (최근 거래)")
if not df.empty:
    st.line_chart(df.set_index("timestamp")["latency"])

st.subheader("거래 목록 (최근)")
if not df.empty:
    st.dataframe(df.sort_values("timestamp", ascending=False).reset_index(drop=True))

st.warning("AI 탐지(텔레그램 전송)는 ai_monitor.py가 수행합니다. anomalies.jsonl 파일을 통해 UI에 이상 내역이 집계됩니다.")
