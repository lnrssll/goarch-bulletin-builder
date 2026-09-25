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

Open http://127.0.0.1:8000 and log in. This uses Docker volumes of its own, not the `build/` folder in the repo, so nothing you do here touches the real bulletins. `docker compose down` stops it; `docker compose down -v` also deletes its data.

## Railway

1. **Push** the repo to GitHub. On railway.com, make a new project with *Deploy from GitHub repo*. Railway finds the `Dockerfile` by itself.
2. **Variables:** in the service's *Variables* tab, open the *Raw Editor* and paste the contents of `.env.prod` (`BULLETIN_PASSWORD` and `RAILWAY_RUN_UID=0`).
3. **Volume:** attach a volume to the service with mount path `/app/build`. This is where the Sundays are kept; without it, every redeploy loses them. Railway allows one volume per service, so `archive/` (the downloaded goarch.org pages) isn't kept. It's only a cache, and it starts empty after each redeploy.
4. **Domain:** under *Settings > Networking*, generate a domain, or add your own. Railway provides HTTPS itself.

Each push to the main branch redeploys. A redeploy takes the app down for a moment (Railway never runs two copies with the same volume) and logs everyone out.

If the deploy log says `can't write to /app/build`, `RAILWAY_RUN_UID=0` is missing.

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

The data is in two Docker volumes that survive restarts and rebuilds: `build` (one folder per Sunday, the only thing typed in by hand) and `archive` (the pages downloaded from goarch.org). To keep the earlier Sundays' history, copy the `build/` folder from the computer that made the bulletins until now:

```bash
docker compose cp ./build/. app:/app/build/
docker compose exec -u root app chown -R bulletin /app/build
```

Back up `build` now and then:

```bash
docker compose cp app:/app/build ./build-backup-$(date +%F)
```

## When downloads from goarch.org fail

The page for each Sunday says what went wrong. If it's temporary (goarch.org sometimes blocks automated downloads, especially from servers), trying again later usually works. Until it does, the readings can be typed in by hand under "type them in yourself" or "Edit the readings", and the bulletin is made from those.

If it keeps failing for every Sunday, goarch.org has probably changed its pages and the program needs fixing (see `AGENTS.md`).
