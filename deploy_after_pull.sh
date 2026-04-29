#!/usr/bin/env bash
set -Eeuo pipefail

APP_URL="${APP_URL:-http://127.0.0.1:8000}"
DOMAIN="${DOMAIN:-chat.lafialife.com}"
APP_PORT="${APP_PORT:-8000}"
SETUP_NGINX="${SETUP_NGINX:-1}"
CLEAN_DOCKER="${CLEAN_DOCKER:-1}"
FULL_DOCKER_PRUNE="${FULL_DOCKER_PRUNE:-0}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
export WEB_CONCURRENCY

cd "$(dirname "${BASH_SOURCE[0]}")"

SUDO=""
if [ "${EUID:-$(id -u)}" -ne 0 ]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO="sudo"
  else
    echo "This script needs root privileges to install/start Docker. Run it as root or install sudo." >&2
    exit 1
  fi
fi

DOCKER=(docker)

install_docker() {
  if command -v docker >/dev/null 2>&1; then
    return
  fi

  echo "==> Docker is missing. Installing Docker Engine and Compose plugin"

  if [ "$(uname -s)" != "Linux" ]; then
    echo "Automatic Docker installation is only supported on Linux." >&2
    exit 1
  fi

  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y ca-certificates curl
  elif ! command -v curl >/dev/null 2>&1; then
    echo "curl is required to install Docker automatically." >&2
    exit 1
  fi

  curl -fsSL https://get.docker.com -o /tmp/get-docker.sh
  $SUDO sh /tmp/get-docker.sh
  rm -f /tmp/get-docker.sh

  if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable --now docker
  elif command -v service >/dev/null 2>&1; then
    $SUDO service docker start
  fi
}

ensure_curl() {
  if command -v curl >/dev/null 2>&1; then
    return
  fi

  if command -v apt-get >/dev/null 2>&1; then
    echo "==> Installing curl"
    $SUDO apt-get update
    $SUDO apt-get install -y curl
  else
    echo "curl is required for the deployment health check." >&2
    exit 1
  fi
}

install_nginx() {
  if command -v nginx >/dev/null 2>&1; then
    return
  fi

  echo "==> Installing Nginx"
  if command -v apt-get >/dev/null 2>&1; then
    $SUDO apt-get update
    $SUDO apt-get install -y nginx
  else
    echo "Automatic Nginx installation currently supports apt-based Linux servers." >&2
    exit 1
  fi
}

setup_nginx() {
  if [ "$SETUP_NGINX" != "1" ]; then
    return
  fi

  install_nginx

  echo "==> Configuring Nginx for $DOMAIN -> 127.0.0.1:$APP_PORT"
  $SUDO tee /etc/nginx/sites-available/chatlearning >/dev/null <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};

    client_max_body_size 200M;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 300;
        proxy_send_timeout 300;
    }
}
NGINX

  $SUDO ln -sfn /etc/nginx/sites-available/chatlearning /etc/nginx/sites-enabled/chatlearning
  if [ -e /etc/nginx/sites-enabled/default ]; then
    $SUDO rm -f /etc/nginx/sites-enabled/default
  fi

  $SUDO nginx -t

  if command -v systemctl >/dev/null 2>&1; then
    $SUDO systemctl enable --now nginx
    $SUDO systemctl reload nginx
  elif command -v service >/dev/null 2>&1; then
    $SUDO service nginx restart
  else
    $SUDO nginx -s reload
  fi
}

configure_docker_command() {
  if docker info >/dev/null 2>&1; then
    DOCKER=(docker)
  elif [ -n "$SUDO" ] && $SUDO docker info >/dev/null 2>&1; then
    DOCKER=($SUDO docker)
  else
    echo "Docker is installed but not reachable. Check Docker service status and permissions." >&2
    exit 1
  fi
}

compose() {
  if docker compose version >/dev/null 2>&1; then
    "${DOCKER[@]}" compose "$@"
  elif command -v docker-compose >/dev/null 2>&1; then
    if docker-compose version >/dev/null 2>&1; then
      docker-compose "$@"
    else
      $SUDO docker-compose "$@"
    fi
  else
    echo "Docker Compose is not installed." >&2
    exit 1
  fi
}

echo "==> Deploying ChatLearning from $(pwd)"

install_docker
configure_docker_command
"${DOCKER[@]}" version >/dev/null
ensure_curl
setup_nginx

if [ ! -f .env ]; then
  echo ".env is missing. Create it from .env.example and add production secrets before deploying." >&2
  exit 1
fi

mkdir -p storage/data storage/uploads storage/chroma storage/uploads/videos

echo "==> Current git revision"
git --no-pager log -1 --oneline || true

if [ "$CLEAN_DOCKER" = "1" ]; then
  echo "==> Cleaning Docker build cache"
  "${DOCKER[@]}" builder prune -af
fi

if [ "$FULL_DOCKER_PRUNE" = "1" ]; then
  echo "==> Cleaning unused Docker images, containers, and networks"
  "${DOCKER[@]}" system prune -af
fi

echo "==> Building app image"
compose build app

echo "==> Starting app"
compose up -d app

echo "==> Container status"
compose ps

echo "==> Waiting for app health"
for attempt in $(seq 1 30); do
  if curl -fsS "$APP_URL/webhook/status" >/tmp/chatlearning-health.json; then
    echo "Health check passed:"
    cat /tmp/chatlearning-health.json
    echo
    rm -f /tmp/chatlearning-health.json
    echo "==> Deployment complete"
    exit 0
  fi

  echo "Health check not ready yet ($attempt/30)"
  sleep 2
done

echo "Health check failed. Recent app logs:" >&2
compose logs --tail=120 app >&2
exit 1
