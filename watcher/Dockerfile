FROM python:3.11-alpine

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy watcher script
COPY watcher.py .

# Run with unbuffered output
CMD ["python", "-u", "watcher.py"]
