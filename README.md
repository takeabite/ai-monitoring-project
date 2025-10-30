### 프로젝트 개요
- 가상의 거래 데이터를 실시간 생성 및 기록
- AI 기반 이상 탐지: AutoEncoder(딥러닝) + 룰 베이스(고지연, 고액, 미등록 상점 등)
- 이상 거래 탐지 시 Telegram 알림 및 anomalies.jsonl 파일에 영속화
- Streamlit 대시보드(app.py)에서 실시간 거래 및 이상 내역 시각화 (3초마다 자동 새로고침)

### 주요 기술 및 라이브러리
- Python, pandas, numpy, re, json
- scikit-learn (StandardScaler)
- TensorFlow / Keras (AutoEncoder)
- telegram.Bot (Telegram 알림)
- Streamlit, streamlit_autorefresh, plotly (웹 UI 및 시각화)
- JSONL 파일(anomalies.jsonl)로 이상 이벤트 기록

### 파일 구조 및 주요 파일
- generate_transactions.py : 합성 거래 로그 생성기 (logs/tx_log.txt 기록)
- ai_monitor.py : 로그 모니터링, AutoEncoder 학습/검출, Telegram 전송, anomalies.jsonl 기록
- app.py : Streamlit 대시보드(UI), anomalies.jsonl 및 거래 로그 읽어서 시각화
- config.py : 설정 (LOG_FILE, Telegram 토큰 등)
- .gitignore : 민감 정보 및 로그 파일 제외
    - config.py, logs/tx_logs.txt, logs/tx_log.txt.anomalies.jsonl 등

### 실행 예시
```bash
python generate_transactions.py
python ai_monitor.py
streamlit run app.py
```
- config.py에서 TELEGRAM_TOKEN, TELEGRAM_CHAT_ID 등 설정 필요

### 이상 이벤트 유형
| 키              | 한글 설명                 |
|-----------------|-------------------------|
| autoencoder     | AI 이상(AutoEncoder)     |
| high_latency    | 고지연                   |
| high_amount     | 고액                     |
| failure         | 거래 실패                 |
| burst           | 버스트                    |
| composite       | 복합 이상                 |

### 기타 주의사항
- Telegram 알림을 위해 config.py의 토큰/채팅 ID 반드시 입력
- 민감 정보 및 로그 파일은 .gitignore에 포함, 외부 공개 주의
- anomalies.jsonl 파일이 Streamlit 대시보드에서 이상 이벤트 집계에 사용됨