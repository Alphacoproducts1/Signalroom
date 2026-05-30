FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV PORT=8000
EXPOSE 8000
# shell form so ${PORT} is expanded by the host
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT}
