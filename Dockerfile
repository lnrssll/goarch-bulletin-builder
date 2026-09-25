FROM python:3.13-slim-trixie

# uv from PyPI rather than a container registry: PyPI keeps every release
RUN pip install --no-cache-dir uv==0.12.10

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    TZ=America/Phoenix \
    PORT=8000

WORKDIR /app

COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --locked --no-dev --no-install-project

COPY . .
RUN useradd --system --no-create-home bulletin \
    && mkdir -p build archive \
    && chown bulletin build archive
USER bulletin

EXPOSE 8000

CMD [".venv/bin/python", "web.py", "--host", "0.0.0.0"]
