# Deployment

The web UI ships as one Docker image (`Dockerfile`). It runs the same way on this computer, on Railway, or on your own server behind nginx.

## Settings

The app is configured through environment variables, listed in `.env.example`:

| Variable | |
|---|---|
| `BULLETIN_PASSWORD` | the one password everyone who makes the bulletin shares. Required, or the app refuses to start |
| `RAILWAY_RUN_UID=0` | Railway only: its volumes belong to root, and the app otherwise runs as a regular user |
| `PORT` | set by Railway; the default is 8000 |

Keep the values in two gitignored files, made by copying `.env.example`:
- `.env.local`: for trying the image on this computer. The password can be anything.
- `.env.prod`: the real server's values. This is where the real password lives, so keep it out of git and chat.

The time zone (`America/Phoenix`, which decides what "next Sunday" is) is set in the `Dockerfile`.

## Try it on this computer

```bash
cp .env.example .env.local        # then set BULLETIN_PASSWORD
docker compose up -d --build
docker compose logs -f            # "Bulletin Builder on http://0.0.0.0:8000/" means it's up
```

Open http://127.0.0.1:8000 and log in. This uses Docker volumes of its own, not the `state/` folder in the repo, so nothing you do here touches the real bulletins. `docker compose down` stops it; `docker compose down -v` also deletes its data.

## Railway

1. **Push** the repo to GitHub. On railway.com, make a new project with *Deploy from GitHub repo*. Railway finds the `Dockerfile` by itself.
2. **Variables:** in the service's *Variables* tab, open the *Raw Editor* and paste the contents of `.env.prod` (`BULLETIN_PASSWORD` and `RAILWAY_RUN_UID=0`).
3. **Volume:** attach a volume to the service with mount path `/app/state`. This is where the Sundays and the parish settings are kept; without it, every redeploy loses them. Railway allows one volume per service, so `archive/` (the downloaded goarch.org pages) isn't kept. It's only a cache, and it starts empty after each redeploy.
4. **Domain:** under *Settings > Networking*, generate a domain, or add your own. Railway provides HTTPS itself.

Each push to the main branch redeploys. A redeploy takes the app down for a moment (Railway never runs two copies with the same volume) and logs everyone out.

If the deploy log says `can't write to /app/state`, `RAILWAY_RUN_UID=0` is missing.

A new volume starts with no earlier Sundays, so the hymn-title suggestions and the carrying over of upcoming services start from nothing and build up as Sundays are saved.

## Your own server (nginx and certbot)

On a server with Docker Compose, nginx, certbot (`sudo apt install certbot python3-certbot-nginx`) and a domain name pointed at it:

```bash
git clone <repo-url> /opt/bulletin
cd /opt/bulletin
cp .env.example .env.prod && chmod 600 .env.prod   # then set BULLETIN_PASSWORD
echo "ENV_FILE=.env.prod" > .env                   # tells docker compose to use .env.prod
docker compose up -d --build
```

The app listens on `127.0.0.1:8000`, so only nginx on the same server can reach it. Then nginx and the certificate:

```bash
sudo cp deploy/nginx-site.conf /etc/nginx/sites-available/bulletin
sudo nano /etc/nginx/sites-available/bulletin   # set server_name to your domain
sudo ln -s /etc/nginx/sites-available/bulletin /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d bulletin.example.org
```

Certbot adds the certificate to the nginx config and renews it automatically. Docker restarts the app after crashes and reboots.

To redeploy: `git pull && docker compose up -d --build`. Everyone has to log in again afterwards.

The data is in two Docker volumes that survive restarts and rebuilds: `state` (everything typed in by hand: `state/sundays/`, one folder per Sunday, and `state/settings/`, the parish details changed under Settings) and `archive` (the pages downloaded from goarch.org). To keep the earlier Sundays' history and the settings, copy the `state/` folder from the computer that made the bulletins until now:

```bash
docker compose cp ./state/. app:/app/state/
docker compose exec -u root app chown -R bulletin /app/state
```

## Backups

`state/` is the only thing that can't be made again. There are two kinds of backup, and it's worth having both:

- **Download a backup** (under Settings in the web UI) gives a zip of `state/` without the PDFs and pictures, which are made again when a Sunday is opened. The home page reminds whoever makes the bulletin when the last download is more than five weeks old. It's the one copy that ends up off the server, kept by someone at the church, so it survives the server being lost or its bill going unpaid.
- **On your own server**, a weekly copy of the volume, keeping 12 weeks. Put this in `/etc/cron.d/bulletin-backup` (`%` must be written `\%` in a cron file):

  ```
  # m h dom mon dow user command
  15 3 * * 0 root mkdir -p /var/backups/bulletin && cd /opt/bulletin && docker compose exec -T app tar czf - -C /app state > /var/backups/bulletin/state-$(date +\%F).tar.gz && find /var/backups/bulletin -name 'state-*.tar.gz' -mtime +84 -delete
  ```

  Check a week later that `/var/backups/bulletin` has a file in it. These copies are on the same machine, so they cover mistakes, not the loss of the server.
- **On Railway**, the volume's settings have a backups section that can take them on a schedule; turn on weekly backups there (see Railway's documentation, which changes more often than this file).

To restore on your own server, from a downloaded zip or a weekly copy:

```bash
mkdir restore && cd restore
unzip ../bulletin-backup-2026-10-04.zip          # or: tar xzf /var/backups/bulletin/state-2026-10-04.tar.gz --strip-components=1
docker compose cp ./. app:/app/state/
docker compose exec -u root app chown -R bulletin /app/state
```

Restoring replaces files of the same name and leaves others alone, and the Sundays' PDFs are made again when they're opened.

## When downloads from goarch.org fail

The page for each Sunday says what went wrong. If it's temporary (goarch.org sometimes blocks automated downloads, especially from servers), trying again later usually works. Until it does, the readings can be typed in by hand under "type them in yourself" or "Edit the readings", and the bulletin is made from those.

If it keeps failing for every Sunday, goarch.org has probably changed its pages and the program needs fixing (see `AGENTS.md`).

## Maintenance

For whoever looks after the program. The church's side of this is in `HANDOVER.md`: give them a printed copy with the blanks filled in.

### Once a year

Pick a fixed month (January, say) and:

1. **Update the image** for security fixes in the base image:
   - Your own server: `cd /opt/bulletin && git pull && docker compose build --pull && docker compose up -d && docker image prune -f`.
   - Railway: redeploy the latest deployment, and check the build log shows `python:3.13-slim-trixie` being pulled rather than all cached.
2. **Check it still works:** open the next Sunday and download its readings. If goarch.org changed its pages, the Sunday page says the page "didn't have the expected content"; see "Data sources" in `AGENTS.md`, and add that Sunday's pages to `archive/` as a test case once fixed.
3. **Check the renewals** on the church's handover sheet: the server bill, the domain, and who gets their emails. On your own server, also `sudo certbot renew --dry-run`: certbot's expiry warnings go to the email given when it was set up, which may be nobody's by now.
4. **Check the backups:** the "Last downloaded" date under Settings, and on your own server that `/var/backups/bulletin` has recent files.

### What expires

| What | Until about | Then |
|---|---|---|
| Python 3.13 security fixes | October 2029 | move to a newer Python (below) |
| Debian 13 "trixie", the base image's system | mid-2028 (security), mid-2030 (LTS) | move to a newer `-slim-<debian>` tag (below) |
| Typst 0.15 (`typst<0.16`) | doesn't expire: it only reads files and runs offline | upgrade only if something needs it (below) |

**Moving to a newer Python or Debian:** change the `FROM` tag in the `Dockerfile`, `.python-version` and `requires-python` in `pyproject.toml`, and the `uv` version pinned in the `Dockerfile`. Then `uv lock --upgrade`, `uv run pytest`, and build the image. Compare the preview of a few Sundays before and after: nothing should move.

**Upgrading Typst** (typst-py 0.16 or later) changes how text is set, so the text sizing has to be checked again, as in `tasks/done/001-text-sizing.md`: `uv run text_sizing.py --report`, then compile a spread of dates (a short one, a typical one, 2026-05-17) and check each is 2 pages and well filled. Adjust `glyph_advance_em` in `data/text_metrics.yaml` first if they aren't.

### What usually goes wrong

Over ten years the likely failures aren't in the code:
- **The domain lapses** or **the server bill goes unpaid**: auto-renew, a card that doesn't quietly expire, and more than one person on the billing emails.
- **Nobody knows the password:** it's kept where the handover sheet says, and changing it needs only the Railway account (or `.env.prod` and `docker compose up -d` on your own server).
- **goarch.org changes its pages:** the volunteer can type the readings in meanwhile, so it's never urgent. The scrapers are in `goarch_xml_feed.py` and `digital_chant_stand.py`, and the tests replay every Sunday in `archive/`.
- **goarch.org blocks the server** (Cloudflare bot checks, more common from datacenters): same fallback. If it becomes permanent, downloading with `main.py` from a home connection and copying the Sunday's folder into the volume works too.
