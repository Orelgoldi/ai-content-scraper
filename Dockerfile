FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p data/images

# Expose dashboard port
EXPOSE 8080

# Default: run server (dashboard + scheduled scraping)
CMD ["python", "run.py", "server"]
