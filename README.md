프로젝트명
Transaction Anomaly Monitor (AutoEncoder + Streamlit + Telegram)

개요
합성 거래 로그를 생성(generate_transactions.py) → ai_monitor.py가 AutoEncoder로 이상 탐지(학습/온라인 탐지/재학습) → 이상 발생 시 Telegram 전송 및 anomalies.jsonl에 레코드 저장 → Streamlit UI(app.py)는 로그와 anomalies.jsonl을 읽어 시각화/집계 제공.

주요 기술

Python, pandas, numpy, re
scikit-learn (StandardScaler)
TensorFlow / Keras (AutoEncoder)
python-telegram-bot (Telegram 알림)
Streamlit (웹 UI)
JSONL 파일(anomalies.jsonl)로 이상 영속화
파일 구조(주요)

generate_transactions.py : 합성 거래 로그 생성기
ai_monitor.py : 로그 모니터링, AutoEncoder 학습/검출, Telegram 전송
app.py : Streamlit 대시보드(UI) — ai_monitor가 기록한 anomalies.jsonl 읽음
config.py : 설정 (LOG_FILE, Telegram 토큰 등)