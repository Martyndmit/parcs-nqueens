#!/usr/bin/env bash
# Видалення всіх VM і правил брандмауера ПАРКС (щоб не витрачати кредити).
#   bash deploy/gcp/destroy.sh [N]   # N - скільки воркерів створювали (за замовчуванням 8, зайві пропускаються)
set -uo pipefail

N="${1:-8}"
ZONE="${ZONE:-europe-north1-a}"

NAMES=(parcs-master)
for i in $(seq 1 "$N"); do NAMES+=("parcs-worker-$i"); done
EXISTING=$(gcloud compute instances list --filter="zone:($ZONE)" --format='value(name)')

TO_DELETE=()
for name in "${NAMES[@]}"; do
  if echo "$EXISTING" | grep -qx "$name"; then TO_DELETE+=("$name"); fi
done
if [ ${#TO_DELETE[@]} -gt 0 ]; then
  gcloud compute instances delete "${TO_DELETE[@]}" --zone="$ZONE" --quiet
fi

for rule in parcs-allow-internal parcs-allow-ui; do
  gcloud compute firewall-rules delete "$rule" --quiet 2>/dev/null || true
done
echo "Done. Check: gcloud compute instances list"
