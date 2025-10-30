# generate_transactions.py
import random, time, datetime, os

LOG_DIR = "./logs"
os.makedirs(LOG_DIR, exist_ok=True)
FNAME = os.path.join(LOG_DIR, "tx_log.txt")

MERCHANTS = ["CU","GS25","Starbucks","Amazon","NaverPay","Homeplus"]
REGIONS = ["Seoul","Busan","Incheon","Daegu","Gwangju"]

# 이상 옵션 확률 조정
PROB_HIGH_LATENCY = 0.02
PROB_HIGH_AMOUNT = 0.015
PROB_UNKNOWN_MERCHANT = 0.005
PROB_UNKNOWN_REGION = 0.005
PROB_FAILURE = 0.03
PROB_OFF_HOUR = 0.02
PROB_BURST = 0.01
PROB_CARD_TEST = 0.005   # 소액 반복 (card testing)
PROB_MERCHANT_SPIKE = 0.004  # 특정 상점에서 짧은 시간에 집중

def generate_tx_line(now=None):
    if now is None:
        now = datetime.datetime.now()

    # 기본 정상 분포
    status = random.choices(["SUCCESS","FAIL"], weights=[0.96,0.04])[0]
    latency = max(10, random.gauss(150, 40))   # ms
    if status == "FAIL":
        latency *= random.uniform(1.8, 4.0)

    merchant = random.choice(MERCHANTS)
    region = random.choice(REGIONS)
    amount = round(max(100, random.gauss(30000, 15000)))  # KRW

    # 이상 시나리오 적용
    # 1) 고지연
    if random.random() < PROB_HIGH_LATENCY:
        latency = random.uniform(1000, 8000)

    # 2) 고액 거래
    if random.random() < PROB_HIGH_AMOUNT:
        amount = round(random.uniform(500000, 5000000))

    # 3) 익숙치 않은 상점/지역 (unknown -> featurize에서 미등록 처리)
    if random.random() < PROB_UNKNOWN_MERCHANT:
        merchant = "odd_merchant_" + str(random.randint(1,999))
    if random.random() < PROB_UNKNOWN_REGION:
        region = "odd_region_" + str(random.randint(1,999))

    # 4) 실패(일부는 지연 증가)
    if random.random() < PROB_FAILURE:
        status = "FAIL"
        latency = max(1.0, latency * random.uniform(1.5, 5.0))

    # 5) 오프아워(심야 거래)
    if random.random() < PROB_OFF_HOUR:
        off_hour = random.choice([0,1,2,3,4])
        now = now.replace(hour=off_hour, minute=random.randint(0,59), second=random.randint(0,59))

    # 6) 카드테스트(소액 반복) — 반환되는 라인에는 차이가 없지만 발생 빈도가 높음
    if random.random() < PROB_CARD_TEST:
        amount = round(random.uniform(100, 1500))  # 아주 작은 금액

    # 7) 상점 스파이크: 특정 상점에서 다수 거래를 빠르게 발생시키기 위해 호출 측에서 burst 모드 사용
    # 8) 버스트(한 번에 여러 거래) 핸들링은 main()에서 실행

    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
    return f"[{timestamp}] status={status} latency={latency:.1f}ms merchant={merchant} region={region} amount={amount}"

def main(rate_per_sec=1.0):
    print(f"Starting transaction generator -> {FNAME}")
    cnt = 0
    try:
        with open(FNAME, "a", encoding="utf-8") as f:
            while True:
                now = datetime.datetime.now()
                lines_to_write = []

                # 버스트 이벤트 발생 시 여러 거래를 빠르게 append
                if random.random() < PROB_BURST:
                    burst_count = random.randint(3, 12)
                    for i in range(burst_count):
                        lines_to_write.append(generate_tx_line(now + datetime.timedelta(milliseconds=i*5)))
                elif random.random() < PROB_MERCHANT_SPIKE:
                    # 특정 merchant spike: 같은 merchant로 연속 소수 거래 생성
                    m = random.choice(MERCHANTS)
                    for i in range(random.randint(4,12)):
                        line = generate_tx_line(now + datetime.timedelta(milliseconds=i*20))
                        # replace merchant to spike merchant
                        line = line.replace("merchant=" + line.split("merchant=")[1].split()[0], f"merchant={m}")
                        lines_to_write.append(line)
                else:
                    lines_to_write.append(generate_tx_line(now))

                for line in lines_to_write:
                    f.write(line + "\n")
                    cnt += 1

                f.flush()
                if cnt % 50 == 0:
                    print(f"[heartbeat] {cnt} txs -> last: {lines_to_write[-1].split(' ',1)[1]}")
                # poisson-like spacing
                wait = random.expovariate(rate_per_sec) if rate_per_sec>0 else 1.0
                time.sleep(max(0.01, wait))
    except KeyboardInterrupt:
        print("Stopped by user")

if __name__ == "__main__":
    main(rate_per_sec=2.0)
