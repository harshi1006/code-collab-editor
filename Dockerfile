# ── Base image ──────────────────────────────────────────────
FROM python:3.11-slim

# ── Install system runtimes────────────────────────────
RUN apt-get update && apt-get install -y \
    # JavaScript
    nodejs npm \
    # Java
    default-jdk \
    # C / C++
    gcc g++ \
    # Go
    golang \
    # Bash (already in slim but explicit)
    bash \
    # PHP
    php \
    # Ruby
    ruby \
    # Rust dependencies
    curl \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ── Rust install (rustup se) ─────────────────────────────────
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

# ── TypeScript (ts-node) ─────────────────────────────────────
RUN npm install -g ts-node typescript

# ── Working directory ────────────────────────────────────────
WORKDIR /app

# ── Python dependencies ──────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── App files ────────────────────────────────────────────────
COPY . .

# ── Port ─────────────────────────────────────────────────────
EXPOSE 5000

# ── Start ────────────────────────────────────────────────────
CMD ["gunicorn", "--worker-class", "eventlet", "-w", "1", "--bind", "0.0.0.0:5000", "app:app"]
