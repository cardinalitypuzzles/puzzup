FROM python:3.10.9

ENV PYTHONUNBUFFERED 1
ENV GIT_PYTHON_REFRESH=quiet

WORKDIR /usr/src/puzzup

# # Install Poetry
ENV POETRY_VERSION=1.6.1
RUN curl -sSL https://install.python-poetry.org | python3 -
ENV PATH="/root/.local/bin:$PATH"

RUN poetry config virtualenvs.create false
COPY pyproject.toml poetry.lock ./
RUN poetry lock
RUN poetry install
