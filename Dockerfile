# ── Base image ──────────────────────────────────────────────
FROM python:3.11-slim

# ── System runtimes install karo ────────────────────────────
RUN apt-get update && apt-get install -y \
    nodejs npm \
    default-jdk \
    gcc g++ \
    golang \
    bash \
    php \
    ruby \
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Rust install ─────────────────────────────────────────────
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# ── Pre-warm Go cache (build a hello world at image build time)
ENV GOPATH=/tmp/gopath
ENV GOCACHE=/tmp/gocache
RUN mkdir -p /tmp/gowarm && \
    echo 'package main\nimport "fmt"\nfunc main(){fmt.Println("ok")}' > /tmp/gowarm/main.go && \
    cd /tmp/gowarm && \
    go mod init warmup && \
    go build -o /tmp/gowarm/out . && \
    rm -rf /tmp/gowarm

# ── Working directory ────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ──────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App files ────────────────────────────────────────────────
COPY . .

# ── Port ─────────────────────────────────────────────────────
EXPOSE 10000

# ── Start ────────────────────────────────────────────────────
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:10000", "--timeout", "120", "app:app"]
