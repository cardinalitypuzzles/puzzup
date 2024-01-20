# syntax=docker/dockerfile:1
FROM python:3.9.17-slim

RUN apt-get update \
	&& apt-get install -y --no-install-recommends \
		postgresql-client curl build-essential git awscli nginx \
	&& rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PIP_DEFAULT_TIMEOUT=100 \
    POETRY_HOME="/opt/poetry" \
    POETRY_NO_INTERACTION=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    VIRTUAL_ENV="/venv"

# prepend poetry and venv to path
ENV PATH="$POETRY_HOME/bin:$VIRTUAL_ENV/bin:$PATH"

# prepare virtual env
RUN python -m venv $VIRTUAL_ENV

WORKDIR /usr/src/app
ENV PYTHONPATH="/usr/src/app:$PYTHONPATH"

COPY <<'EOF' /etc/nginx/sites-available/default
server {
    listen 80;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static/ {
        root /usr/src/app/;
    }

    location /healthcheck {
        return 200;
    }
}
EOF

RUN --mount=type=cache,target=/root/.cache \
    curl -sSL https://install.python-poetry.org | python -

COPY poetry.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-root --only main

COPY . .
RUN python manage.py collectstatic

COPY --chmod=755 <<'EOF' /usr/src/app/start.sh
#!/bin/bash
set -eux
set -o pipefail

aws ssm get-parameter --output text --query Parameter.Value --with-decryption --name puzzup-env > .env
mkdir credentials
aws ssm get-parameter --output text --query Parameter.Value --with-decryption --name puzzup-drive-credentials > credentials/drive-credentials.json
python manage.py migrate
nginx
gunicorn -w "$(nproc)" puzzup.wsgi:application
EOF

EXPOSE 80
CMD ["./start.sh"]
