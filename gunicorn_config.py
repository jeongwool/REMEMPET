import os

# Worker 설정 - 메모리 최소화
workers = 1  # Free 플랜에서는 1개만!
worker_class = "sync"
threads = 2

# 타임아웃 설정
timeout = 120
graceful_timeout = 120
keepalive = 5

# 메모리 관리
max_requests = 100  # 100개 요청마다 worker 재시작
max_requests_jitter = 20

# 로깅
loglevel = "info"
accesslog = "-"
errorlog = "-"

# 바인딩
bind = f"0.0.0.0:{os.environ.get('PORT', 10000)}"

# 프리로드 - 메모리 공유
preload_app = True
