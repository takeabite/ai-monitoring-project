# config.py
# Telegram 설정
TELEGRAM_TOKEN = "8241727073:AAGDxtB-nvX4axPCnGczOGBqo9xryO3GMdw"
TELEGRAM_CHAT_ID = "5100081132"

# 이상탐지/운영 파라미터
CONTAMINATION = 0.03    # AutoEncoder에서는 참고용; 실제 threshold는 재구성오차로 결정
MIN_WARMUP = 200        # AutoEncoder 초기학습에 필요한 샘플 수
RETRAIN_EVERY = 200     # 새로운 샘플 수집 후 재학습 간격
LOG_FILE = "./logs/tx_log.txt"
