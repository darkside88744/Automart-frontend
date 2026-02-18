FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    default-libmysqlclient-dev \
    build-essential \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy requirements from the root of your project
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

# Copy everything from your root into /app
COPY . .

# Setting the PYTHONPATH allows Python to find 'Automotive' as a module
ENV PYTHONPATH=/app/Automotive

EXPOSE 8000

# We use the Automotive sub-folder as the pythonpath to find wsgi.application
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--pythonpath", "Automotive", "Automotive.wsgi:application"]