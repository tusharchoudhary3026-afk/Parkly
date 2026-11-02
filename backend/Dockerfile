FROM python:3.12-slim AS runtime
WORKDIR /srv
COPY requirements.txt ./
RUN pip install --no-cache-dir --timeout 1800 --retries 10 --index-url https://pypi.org/simple -r requirements.txt
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini pyproject.toml ./
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM runtime AS test
RUN pip install --no-cache-dir --timeout 1800 --retries 10 --index-url https://pypi.org/simple pytest pytest-asyncio httpx
COPY tests ./tests
CMD ["python", "-m", "pytest", "-q", "-s"]
