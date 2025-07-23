# Use an official Python runtime as the base image
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update --fix-missing && \
    apt-get install -y --fix-missing build-essential git && \
    rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV FASTAPI_APP=rfp_assistant.py 
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the port
EXPOSE 6001

# Run the FastAPI application
CMD ["fastapi", "run", "--host=0.0.0.0", "--port=6001"]