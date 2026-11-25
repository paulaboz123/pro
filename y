uv run -m studio index search "sprint planning" -k 5
uv run -m studio contextual
tar -czf kb.tgz -C data --exclude=./input --exclude=./output --exclude=./index --exclude=./brand --exclude=./avatars .
kubectl -n <namespace> cp kb.tgz "<pod>:/tmp/kb.tgz"
kubectl -n <namespace> exec <pod> -- tar -xzf /tmp/kb.tgz -C /app/data --no-same-owner --no-overwrite-dir
kubectl -n <namespace> exec <pod> -- python -m studio index build
kubectl -n <namespace> exec <pod> -- python -m studio doctor
