#!/bin/bash
# Startup-script для VM з Container-Optimized OS (COS).
# Запускає вузол ПАРКС (образ hummer12007/parcs-node) у Docker з мережею хоста.
#
# Замінює застарілий `gcloud compute instances create-with-container`
# (container startup agent вимкнено Google 31.07.2026).
#
# Роль вузла береться з метаданих VM:
#   parcs-args  = "master"  або  "worker <внутрішній IP master>"
#   parcs-image = образ Docker (необов'язково)
set -u

MD="http://metadata.google.internal/computeMetadata/v1/instance/attributes"
PARCS_ARGS="$(curl -sf -H 'Metadata-Flavor: Google' "$MD/parcs-args")"
IMAGE="$(curl -sf -H 'Metadata-Flavor: Google' "$MD/parcs-image" || true)"
IMAGE="${IMAGE:-hummer12007/parcs-node}"
NAME="parcs"

echo "PARCS startup: args='${PARCS_ARGS}', image='${IMAGE}'"

# COS за замовчуванням блокує вхідні з'єднання на рівні хоста:
# ПАРКС використовує порт 8080 (веб-інтерфейс / API) і випадкові порти (Flask воркерів, Pyro4)
iptables -w -A INPUT -j ACCEPT

docker rm -f "$NAME" >/dev/null 2>&1 || true
until docker pull "$IMAGE"; do
  echo "docker pull failed, retry in 5 s"; sleep 5
done

# --network host: так само, як працював контейнер у create-with-container;
# воркер дізнається свою IP-адресу через `hostname -I`
docker run -d --name "$NAME" --network host --restart always \
  -e PARCS_ARGS="$PARCS_ARGS" "$IMAGE"
