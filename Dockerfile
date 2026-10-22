FROM python:3.11-slim-bookworm

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 dashboard
COPY --chown=dashboard:dashboard . .
USER dashboard
EXPOSE 8070
CMD ["python", "app.py"]

