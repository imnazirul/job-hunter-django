FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Test tooling is not shipped to production. docker-compose sets this to 1 so
# the local image can still run pytest.
ARG INSTALL_DEV=0

COPY requirements.txt requirements-dev.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && if [ "$INSTALL_DEV" = "1" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi

COPY . .

RUN mkdir -p media staticfiles

# Baked into the image so no request pays for it. The key is a build-time
# throwaway: settings refuse to import without one, and collectstatic never
# signs anything.
RUN DJANGO_SECRET_KEY=build-only-not-a-runtime-key python manage.py collectstatic --noinput

EXPOSE 8000

# The platform picks the port; ${PORT:-8000} keeps `docker run` working too.
CMD ["sh", "-c", "python manage.py migrate --noinput && exec gunicorn jobhunter.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers ${WEB_CONCURRENCY:-2} --timeout ${WEB_TIMEOUT:-120} --access-logfile -"]
