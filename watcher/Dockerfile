FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy watcher script
COPY watcher.py .

# Make script executable
RUN chmod +x watcher.py

# Run with unbuffered output for real-time logging
CMD ["python", "-u", "watcher.py"]
