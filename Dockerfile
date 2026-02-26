# Python 3.9 기본 이미지 사용
FROM python:3.9-slim

# FFmpeg 및 필요한 패키지 설치
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# 작업 디렉토리 설정
WORKDIR /app

# 애플리케이션 종속성 설치
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 애플리케이션 코드 복사
COPY . .

# 환경 변수 설정
ENV PORT=8080

# 서버 실행
CMD exec gunicorn --bind :$PORT main:app