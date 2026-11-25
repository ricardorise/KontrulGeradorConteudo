FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends openssh-client ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .
COPY migrations ./migrations
# O ssh (chamadas ao Hermes) exige que o uid do processo exista em /etc/passwd; 1000 = dono da chave no servidor.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin studio \
 && mkdir -p /data/media && chown 1000:1000 /data/media
ENV PYTHONUNBUFFERED=1 STUDIO_MEDIA_DIR=/data/media
EXPOSE 8100
CMD ["uvicorn", "studio.bootstrap:create_app", "--factory", "--host", "0.0.0.0", "--port", "8100"]
