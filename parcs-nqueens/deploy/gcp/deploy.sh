#!/usr/bin/env bash
# Розгортання ПАРКС (PARCS-Python): 1 master + N воркерів у Google Compute Engine.
#
#   bash deploy/gcp/deploy.sh [N]   # N - кількість воркерів (за замовчуванням 4)
#
# Змінні середовища (необов'язково):
#   ZONE=europe-north1-a     зона (як у методичці)
#   MACHINE=n1-standard-1    тип VM: 1 vCPU, без "burst" - стабільні заміри часу
#   ALLOW_FROM=0.0.0.0/0     з яких адрес відкрити веб-інтерфейс :8080
#                            (краще вказати свою IP: ALLOW_FROM=1.2.3.4/32)
#   IMAGE=hummer12007/parcs-node
#
# Перед запуском: gcloud auth login; gcloud config set project <PROJECT_ID>
# (у Google Cloud Shell gcloud уже налаштований).
set -euo pipefail

N="${1:-${WORKERS:-4}}"
ZONE="${ZONE:-europe-north1-a}"
MACHINE="${MACHINE:-n1-standard-1}"
ALLOW_FROM="${ALLOW_FROM:-0.0.0.0/0}"
IMAGE="${IMAGE:-hummer12007/parcs-node}"
DIR="$(cd "$(dirname "$0")" && pwd)"
COMMON=(--zone="$ZONE" --machine-type="$MACHINE"
        --image-family=cos-stable --image-project=cos-cloud
        --tags=parcs --metadata-from-file=startup-script="$DIR/startup.sh")

echo ">> Project: $(gcloud config get-value project 2>/dev/null), zone: $ZONE, machine: $MACHINE, workers: $N"
gcloud services enable compute.googleapis.com

echo ">> Firewall rules"
if ! gcloud compute firewall-rules describe parcs-allow-internal >/dev/null 2>&1; then
  # трафік між вузлами ПАРКС (реєстрація воркерів, HTTP-API, Pyro4 на випадкових портах)
  gcloud compute firewall-rules create parcs-allow-internal --network=default \
    --direction=INGRESS --action=ALLOW --rules=all \
    --source-tags=parcs --target-tags=parcs
fi
if ! gcloud compute firewall-rules describe parcs-allow-ui >/dev/null 2>&1; then
  # веб-інтерфейс і REST API master
  gcloud compute firewall-rules create parcs-allow-ui --network=default \
    --direction=INGRESS --action=ALLOW --rules=tcp:8080 \
    --source-ranges="$ALLOW_FROM" --target-tags=parcs
fi

echo ">> Master"
gcloud compute instances create parcs-master "${COMMON[@]}" \
  --metadata="parcs-args=master,parcs-image=$IMAGE"

MASTER_INT="$(gcloud compute instances describe parcs-master --zone="$ZONE" \
  --format='get(networkInterfaces[0].networkIP)')"
MASTER_EXT="$(gcloud compute instances describe parcs-master --zone="$ZONE" \
  --format='get(networkInterfaces[0].accessConfigs[0].natIP)')"
echo "   internal IP: $MASTER_INT, external IP: $MASTER_EXT"

echo ">> Workers"
NAMES=()
for i in $(seq 1 "$N"); do NAMES+=("parcs-worker-$i"); done
gcloud compute instances create "${NAMES[@]}" "${COMMON[@]}" \
  --metadata="parcs-args=worker $MASTER_INT,parcs-image=$IMAGE"

echo ">> Waiting for PARCS: http://$MASTER_EXT:8080 (Docker image pull takes 1-3 min)"
for _ in $(seq 1 60); do
  COUNT="$(curl -s -m 5 "http://$MASTER_EXT:8080/api/worker" 2>/dev/null \
           | grep -o '"id"' | wc -l || true)"
  echo "   registered workers: ${COUNT:-0}/$N"
  if [ "${COUNT:-0}" -ge "$N" ]; then break; fi
  sleep 10
done

cat <<EOF

PARCS is up.
  Web UI:   http://$MASTER_EXT:8080
  Workers:  http://$MASTER_EXT:8080/api/worker
  Benchmark:
    python3 bench/bench.py --master http://$MASTER_EXT:8080 --n 15 --workers 1,2,3,4 --repeats 3 --sequential --out results/gcp_n15.csv
  Delete everything when done:  bash deploy/gcp/destroy.sh $N
EOF
