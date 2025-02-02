# syntax=docker/dockerfile:1
FROM python:3.12-slim

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

RUN --mount=type=cache,target=/root/.cache \
    curl -sSL https://install.python-poetry.org | python -

COPY poetry.lock pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache \
    poetry install --no-root --only main

COPY . .
