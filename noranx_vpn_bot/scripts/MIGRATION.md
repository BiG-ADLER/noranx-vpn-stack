# NoranX Stack Migration Guide

Portable backup/restore for moving the full stack (bot, Marzban, limiters, nginx, TLS) to another VPS.

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/stack_backup.sh` | Create unified archive |
| `scripts/stack_restore.sh` | Restore archive on new server |
| `scripts/backup.sh` | Legacy bot-only wrapper (`--bot-only`) |
| `scripts/restore_validate.sh` | Post-restore validation gate |

## Backup (source server)

```bash
cd /root/noranx_vpn_bot
sudo ./scripts/stack_backup.sh
```

Options:

- `--output /path/to/backups` — custom output directory
- `--skip-logs` — omit bot log tarball
- `--skip-tls` — omit Let's Encrypt certificates (re-issue on new server)
- `--dry-run` — preflight + staging only (no archive, Marzban not stopped)

Output: `backups/noranx-stack-<UTC_TS>.tar.gz` (mode `600`, contains secrets).

Copy off-server:

```bash
scp backups/noranx-stack-*.tar.gz user@new-server:/root/
```

## Restore (destination server)

### Prerequisites

- Docker + Docker Compose
- nginx
- Python 3.12+
- Root access

### Steps

1. Install Docker/nginx on the new VPS.
2. Copy the archive and this repo (or extract `bot/project/source.tar` from the archive).
3. Run restore:

```bash
cd /root/noranx_vpn_bot
sudo ./scripts/stack_restore.sh /root/noranx-stack-XXXX.tar.gz --target-ip NEW_PUBLIC_IP
```

Options:

- `--target-ip IP` — replace old public IP in restored `.env`
- `--skip-dns` — skip DNS verify/update
- `--skip-tls` — skip Let's Encrypt restore (use certbot instead)
- `--dry-run` — verify archive checksums only
- `--skip-validate` — skip post-restore checks

4. Update DNS (manual or automatic):

```bash
export CLOUDFLARE_API_TOKEN=...
export TARGET_IP=NEW_PUBLIC_IP
sudo ./scripts/restore_update_dns.sh
```

5. Validate:

```bash
sudo ./scripts/restore_validate.sh
```

## Archive contents

```
staging-<TS>/
  MANIFEST.json
  CHECKSUMS.sha256
  meta/               # hostname, IP, docker ps, table counts
  bot/                # postgres, redis, .env, source
  marzban/            # /var/lib/marzban + /opt/marzban config
  infrastructure/     # limiters, nginx, TLS, systemd
```

## Environment overrides

| Variable | Default |
|----------|---------|
| `BOT_ROOT` | `/root/noranx_vpn_bot` |
| `MARZBAN_DATA` | `/var/lib/marzban` |
| `MARZBAN_OPT` | `/opt/marzban` |
| `DEVICE_LIMITER_DIR` | `$BOT_ROOT/infrastructure/device-limiter` |
| `IP_LIMITER_CONFIG` | `/opt/marzneshiniplimit/config.json` |
| `BACKUP_ROOT` | `$BOT_ROOT/backups` |

## Rollback

Before restore, a safety snapshot is saved to:

```
/root/restore-safety/pre-<TS>/
```

To roll back Marzban manually:

```bash
sudo ./scripts/restore_rollback.sh
```

## Security

Archives contain `.env`, database dumps, TLS private keys, and Marzban credentials. Store offline with `chmod 600`. Never commit to git.

## Troubleshooting

| Issue | Action |
|-------|--------|
| "Something went wrong" saving Marzban core | Check `docker logs marzban-marzban-1`; ensure `iran.dat` mount exists |
| Restore validation fails on device limiter | `cd infrastructure/device-limiter && docker compose up -d --build` |
| Bot port 8080 in use | `./scripts/start.sh` kills stale processes first |
| Checksum failure | Re-copy archive; do not edit files inside staging |

Verify archive integrity:

```bash
tmpdir=$(mktemp -d)
tar -xzf backups/noranx-stack-*.tar.gz -C "$tmpdir"
staging=$(find "$tmpdir" -maxdepth 1 -type d -name 'staging-*' | head -1)
(cd "$staging" && sha256sum -c CHECKSUMS.sha256)
```

Dry-run restore:

```bash
sudo ./scripts/stack_restore.sh backups/noranx-stack-*.tar.gz --dry-run
```
