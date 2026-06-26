FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl unzip \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deno.land/install.sh | DENO_INSTALL=/usr/local sh
RUN pip install --no-cache-dir yt-dlp

RUN mkdir -p /root/.config/yt-dlp && \
    printf "%s\n" "--remote-components ejs:github" "--cookies /data/cookies.txt" > /root/.config/yt-dlp/config

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .
COPY database.py .
COPY auth.py .

RUN mkdir -p /data

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
