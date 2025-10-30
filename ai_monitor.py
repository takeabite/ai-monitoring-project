# ai_monitor.py
import re, time, os, json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from collections import deque, defaultdict, Counter
from sklearn.preprocessing import StandardScaler
import tensorflow as tf
from tensorflow import keras
from telegram import Bot
import asyncio
from config import TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, MIN_WARMUP, RETRAIN_EVERY, LOG_FILE

# ---- anomaly output file ----
ANOMALY_FILE = LOG_FILE + ".anomalies.jsonl"

# ---- Telegram bot ----
bot = Bot(token=TELEGRAM_TOKEN)
def send_alert(msg):
    asyncio.run(send_alert_async(msg))
    
async def send_alert_async(msg):
    print(msg)
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("Telegram send failed:", e)


# ---- parsing ----
TX_PATTERN = re.compile(
    r"\[(?P<ts>[^\]]+)\]\s+status=(?P<status>\w+)\s+latency=(?P<lat>[\d\.]+)ms\s+merchant=(?P<merchant>\S+)\s+region=(?P<region>\S+)\s+amount=(?P<amount>[\d\.]+)"
)

def parse_lines(lines):
    rows = []
    for L in lines:
        m = TX_PATTERN.search(L)
        if m:
            d = m.groupdict()
            rows.append({
                "timestamp": d["ts"],
                "status": 1 if d["status"]=="SUCCESS" else 0,
                "latency": float(d["lat"]),
                "merchant": d["merchant"],
                "region": d["region"],
                "amount": float(d["amount"]),
                "raw": L.strip()
            })
    if not rows:
        return pd.DataFrame(columns=["timestamp","status","latency","merchant","region","amount","raw"])
    return pd.DataFrame(rows)

# ---- feature engineering ----
def featurize(df, merchant_map=None, region_map=None, scaler:StandardScaler=None):
    # map merchants and regions to integers (consistent mapping)
    if merchant_map is None:
        merchant_map = {m:i for i,m in enumerate(sorted(df["merchant"].unique()))}
    if region_map is None:
        region_map = {r:i for i,r in enumerate(sorted(df["region"].unique()))}
    df = df.copy()
    df["merchant_id"] = df["merchant"].map(merchant_map).fillna(-1).astype(int)
    df["region_id"] = df["region"].map(region_map).fillna(-1).astype(int)

    # numeric features: latency, amount, status, merchant_id, region_id, hour
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    X = df[["latency","amount","status","merchant_id","region_id","hour"]].astype(float).values

    # scale
    if scaler is None:
        scaler = StandardScaler()
        Xs = scaler.fit_transform(X)
    else:
        Xs = scaler.transform(X)
    return Xs, scaler, merchant_map, region_map

# ---- AutoEncoder model builder ----
def build_autoencoder(input_dim):
    inputs = keras.Input(shape=(input_dim,))
    x = keras.layers.Dense(32, activation="relu")(inputs)
    x = keras.layers.Dense(16, activation="relu")(x)
    encoded = keras.layers.Dense(8, activation="relu")(x)

    x = keras.layers.Dense(16, activation="relu")(encoded)
    x = keras.layers.Dense(32, activation="relu")(x)
    outputs = keras.layers.Dense(input_dim, activation="linear")(x)

    model = keras.Model(inputs, outputs)
    model.compile(optimizer="adam", loss="mse")
    return model

# ---- Monitor loop ----
def monitor_log():
    # rolling buffer for training (deque of raw lines)
    buffer_lines = deque(maxlen=5000)  # keep recent 5000 lines
    merchant_map = None
    region_map = None
    scaler = None
    model = None
    threshold = None
    processed = 0

    # short-term structures for behavioral rules
    recent_window = deque()  # (timestamp:datetime, merchant, amount)
    merchant_windows = defaultdict(deque)  # merchant -> deque of timestamps
    WINDOW_SEC = 60  # sliding window for velocity/spike/card testing

    last_size = 0
    print("Starting AI monitor - watching", LOG_FILE)
    while True:
        if not os.path.exists(LOG_FILE):
            print("Log file not found. waiting...")
            time.sleep(2); continue

        # read new lines (tail-like)
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            f.seek(last_size)
            new_lines = f.readlines()
            last_size = f.tell()

        if new_lines:
            for l in new_lines:
                buffer_lines.append(l)

            buffer_df = parse_lines(list(buffer_lines))
            if buffer_df.empty:
                time.sleep(1); continue

            # initial warmup: collect MIN_WARMUP then train
            if model is None and len(buffer_df) >= MIN_WARMUP:
                print(f"Warmup reached ({len(buffer_df)}). Training AutoEncoder...")
                X, scaler, merchant_map, region_map = featurize(buffer_df, None, None, None)
                model = build_autoencoder(X.shape[1])
                model.fit(X, X, epochs=20, batch_size=32, verbose=0)
                rec = np.mean((model.predict(X) - X)**2, axis=1)
                threshold = np.percentile(rec, 97.5)
                print("Model trained. threshold set to:", threshold)
                send_alert(f"✅ AI model trained on {len(X)} samples. anomaly threshold={threshold:.4f}")
                processed = len(buffer_df)
                continue

            # after model exists: do online detection for the new_lines only
            if model is not None:
                new_df = parse_lines(new_lines)
                if not new_df.empty:
                    # autoencoder detection
                    X_new, _, _, _ = featurize(new_df, merchant_map, region_map, scaler)
                    X_pred = model.predict(X_new)
                    rec_err = np.mean((X_pred - X_new)**2, axis=1)
                    idxs = np.where(rec_err > threshold)[0]

                    # behavioral / rule-based detection per row
                    now = datetime.utcnow()
                    for i, row in new_df.reset_index(drop=True).iterrows():
                        types = []
                        # autoencoder flag
                        if i in idxs:
                            types.append("autoencoder")

                        # rule thresholds
                        if row["latency"] > 1000:
                            types.append("high_latency")
                        if row["amount"] > 500000:   # 고액 기준 (환경에 맞게 조정)
                            types.append("high_amount")
                        if str(row["merchant"]).startswith("odd_"):
                            types.append("unknown_merchant")
                        if str(row["region"]).startswith("odd_region"):
                            types.append("unknown_region")
                        if row["status"] == 0:
                            types.append("failure")
                        hour = pd.to_datetime(row["timestamp"]).hour
                        if hour in {0,1,2,3,4}:
                            types.append("off_hour")

                        # update short-term windows for behavioral patterns
                        ts = pd.to_datetime(row["timestamp"])
                        recent_window.append((ts, row["merchant"], row["amount"]))
                        merchant_windows[row["merchant"]].append(ts)

                        # pop expired
                        cutoff = ts - pd.Timedelta(seconds=WINDOW_SEC)
                        while recent_window and recent_window[0][0] < cutoff:
                            recent_window.popleft()
                        while merchant_windows[row["merchant"]] and merchant_windows[row["merchant"]][0] < cutoff:
                            merchant_windows[row["merchant"]].popleft()

                        # burst: many overall transactions in short time
                        if len([x for x in recent_window if x[0] >= cutoff]) >= 8:
                            types.append("burst")

                        # card testing: same merchant small amounts many times in window
                        small_count = sum(1 for t,m,a in recent_window if m == row["merchant"] and a < 2000)
                        if small_count >= 6:
                            types.append("card_testing")

                        # merchant spike / velocity: merchant had many tx in window
                        if len(merchant_windows[row["merchant"]]) >= 10:
                            types.append("merchant_spike")

                        # composite: multiple flags
                        if sum(1 for _ in types) >= 3:
                            types.append("composite")

                        if types:
                            # prepare anomaly record
                            an = {
                                "detected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                "timestamp": row["timestamp"],
                                "merchant": row["merchant"],
                                "region": row["region"],
                                "amount": float(row["amount"]),
                                "latency": float(row["latency"]),
                                "status": int(row["status"]),
                                "types": sorted(list(set(types))),
                                "err": float(rec_err[i]) if i in idxs else None,
                                "raw": row.get("raw", "")
                            }
                            # append to anomaly file
                            try:
                                os.makedirs(os.path.dirname(ANOMALY_FILE) or ".", exist_ok=True)
                                with open(ANOMALY_FILE, "a", encoding="utf-8") as af:
                                    af.write(json.dumps(an, ensure_ascii=False) + "\n")
                            except Exception as e:
                                print("Failed to write anomaly file:", e)

                            # send Telegram (concise)
                            try:
                                send_alert(f"🚨 Anomaly [{', '.join(an['types'])}] merchant={an['merchant']} amount={an['amount']} latency={an['latency']:.1f} err={an['err']}")
                            except Exception:
                                pass

                    # periodic retrain to adapt to concept drift
                    processed += len(new_df)
                    if processed >= RETRAIN_EVERY:
                        print("Retraining AutoEncoder with latest buffer...")
                        X_full, scaler, merchant_map, region_map = featurize(buffer_df, merchant_map, region_map, scaler)
                        model = build_autoencoder(X_full.shape[1])
                        model.fit(X_full, X_full, epochs=10, batch_size=32, verbose=0)
                        rec = np.mean((model.predict(X_full) - X_full)**2, axis=1)
                        threshold = np.percentile(rec, 97.5)
                        processed = 0
                        send_alert(f"🔁 AI model retrained on {len(X_full)} samples. new threshold={threshold:.4f}")

        time.sleep(1)

if __name__ == "__main__":
    monitor_log()
