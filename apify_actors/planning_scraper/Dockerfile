# Use Apify's Python + Playwright base image
FROM apify/actor-python-playwright:3.11

# Copy requirements first for caching
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy the actor code (including planning_scraper.py)
COPY . ./

# Playwright browsers are pre-installed in the base image

# Run the actor
CMD ["python", "main.py"]
