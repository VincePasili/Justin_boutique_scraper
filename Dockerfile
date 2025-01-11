# Dockerfile

FROM python:3.9-slim

# Install system dependencies for playwright
RUN apt-get update && apt-get install -y \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libx11-xcb1 \
    libgbm-dev \
    libasound2 \
    libpangocairo-1.0-0 \
    libxshmfence1 \
    fonts-liberation \
    libxrandr2 \
    unzip \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Install pip dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install playwright browsers
RUN playwright install --with-deps chromium

# Copy all project files
COPY . .

# Expose no port needed for scraping, but let's leave the line in case you have metrics
# EXPOSE 8000

CMD ["python", "main.py"]
