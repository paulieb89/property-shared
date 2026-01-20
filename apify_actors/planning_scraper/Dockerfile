# Use Apify's Python + Playwright base image
FROM apify/actor-python-playwright:3.11

# Copy requirements first for caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actor code
COPY . ./

# Copy property_core from parent directory
COPY ../../property_core ./property_core/

# Install playwright browsers
RUN playwright install chromium

# Run the actor
CMD ["python", "main.py"]
