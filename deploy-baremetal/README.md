# NSFW Bare Metal Deployment

This mirrors the `ai-feed-recommendation-system` bare-metal flow:

- GitHub Actions builds and pushes `ghcr.io/<repo>:<sha>`.
- Deployment files are synced to `/home/ansuman/nsfw` on each server.
- `docker compose up -d --no-deps app` rolls servers one at a time.
- The container listens on `8080`; the host publishes it on `127.0.0.1:8001`.
- HAProxy should expose `nsfw.ansuman.yral.com` through bridge port `18082`.

Apply `haproxy-nsfw-snippets.cfg` on both `ansuman-1` and `ansuman-2`.
If the existing frontend uses a host map, append `host2backend.map.append`.

Validate HAProxy before reload:

```bash
haproxy -c -f /etc/haproxy/haproxy.cfg
```
