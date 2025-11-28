import os
import multiprocessing

# Render Free 플랜 최적화
workers = 1  # 절대 늘리지 마세요!
worker_class = "sync"
threads = 2
worker_connections = 50

# 타임아웃 (이미지 생성 고려)
timeout = 180
graceful_timeout = 180
keepalive = 5

# 메모리 관리 - 주기적 재시작
max_requests = 50  # 50개 요청마다 worker 재시작
max_requests_jitter = 10

# 로깅
loglevel = "info"
accesslog = "-"
errorlog = "-"
capture_output = True

# 바인딩
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"

# 메모리 효율
preload_app = True

# Worker 재시작 정책
worker_tmp_dir = "/dev/shm"  # RAM 디스크 사용 (Render 지원)
