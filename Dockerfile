FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    chromium wget \
      libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
      libdrm2 libgbm1 libx11-xcb1 libxcomposite1 \
      libxdamage1 libxrandr2 libxss1 libxtst6 libasound2 \
 && rm -rf /var/lib/apt/lists/*


ENV UCD_CHROMIUM_EXECUTABLE_PATH=/usr/bin/chromium \
    UCD_CHROMIUM_DOWNLOAD_PATH=/usr/local/share/chrome
    
ENV CHROME_EXECUTABLE_PATH=/usr/bin/chromium 


ENV DISPLAY=:99


ENV CHROME_EXECUTABLE_PATH=/usr/bin/google-chrome


RUN which google-chrome || echo "Chrome not found in PATH" \
    && ls -la /usr/bin/google-chrome* || echo "No Chrome binaries found" \
    && google-chrome --version || echo "Chrome version check failed"

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev

ADD . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT []
CMD ["python", "app.py"]