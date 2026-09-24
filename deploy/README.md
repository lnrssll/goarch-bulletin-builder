# Deployment

The web UI runs in Docker, behind nginx with a Let's Encrypt certificate. Once it's up, it needs no attention: Docker restarts it after crashes and reboots, and certbot renews the certificate.

## Prerequisites

On the server:
- Docker with Docker Compose
- nginx
- certbot (`sudo apt install certbot python3-certbot-nginx`)
- A domain name pointed at the server's IP address (certbot needs this)

## First-time setup

### 1. Clone the repo

```bash
git clone <repo-url> /opt/bulletin
cd /opt/bulletin
```

### 2. Set the password

Everyone who makes the bulletin shares one password. Pick a long passphrase.

```bash
sudo sh -c 'echo "BULLETIN_PASSWORD=<long passphrase>" > /etc/bulletin.env'
sudo chmod 600 /etc/bulletin.env
```

### 3. Start the app

```bash
docker compose up -d --build
docker compose logs -f   # "Bulletin Builder on http://0.0.0.0:8000/" means it's up
```

The app listens on `127.0.0.1:8000`, so only nginx on the same server can reach it.

### 4. Configure nginx

```bash
sudo cp deploy/nginx-site.conf /etc/nginx/sites-available/bulletin
sudo nano /etc/nginx/sites-available/bulletin   # set server_name to your domain
sudo ln -s /etc/nginx/sites-available/bulletin /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### 5. Get a TLS certificate

```bash
sudo certbot --nginx -d bulletin.example.org
```

Certbot adds the certificate to the nginx config and sets up automatic renewal. The login only works over HTTPS.

### 6. Bring over earlier Sundays (optional)

The app suggests hymn titles and priests from earlier Sundays and carries the upcoming services over from last week. To keep that history, copy the `build/` folder from the computer that made the bulletins until now:

```bash
docker compose cp ./build/. app:/app/build/
docker compose exec -u root app chown -R bulletin /app/build
```

## Redeploying

```bash
cd /opt/bulletin
git pull
docker compose up -d --build
```

Everyone has to log in again after a redeploy or a server restart.

## Where the data lives

Everything is in two Docker volumes that survive restarts and rebuilds:

| Volume | Holds |
|---|---|
| `build` | one folder per Sunday: the readings, the hymns and services typed in, the PDFs |
| `archive` | the pages downloaded from goarch.org for each Sunday |

Only `build` holds anything typed in by hand. Back it up now and then:

```bash
docker compose cp app:/app/build ./build-backup-$(date +%F)
```

## Useful commands

```bash
docker compose logs -f            # follow the log
docker compose ps                 # is it running?
docker compose restart            # restart the app
docker compose down               # stop it
docker compose exec app sh        # shell inside the container
```

## When downloads from goarch.org fail

The page for each Sunday says what went wrong. If it's temporary (goarch.org sometimes blocks automated downloads, especially from servers), trying again later usually works. Until it does, the readings can be typed in by hand under "type them in yourself" or "Edit the readings", and the bulletin is made from those.

If it keeps failing for every Sunday, goarch.org has probably changed its pages and the program needs fixing (see `AGENTS.md`).
