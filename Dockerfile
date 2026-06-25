FROM ollama/ollama:latest

RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    git \
    curl \
    procps \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /workspace

COPY requirements.txt /tmp/requirements.txt

RUN pip3 install --break-system-packages -r /tmp/requirements.txt

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 11434
EXPOSE 8000
EXPOSE 8080
EXPOSE 9000

ENTRYPOINT ["/start.sh"]