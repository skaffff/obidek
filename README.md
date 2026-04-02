# Office Lunch Board

Simple, config-driven lunch menu collector for nearby restaurants.

- Scrapes each source website with `requests + BeautifulSoup`.
- Writes a single local snapshot file: `data/current_menu.json`.
- Keeps the last successful menu when a restaurant removes menu later in the day.
- Displays only current day from weekly menus.

## Project Structure

- `config/restaurants.yaml` source list and stale policy
- `scraper/update_menus.py` scraper and aggregator
- `data/current_menu.json` generated snapshot (overwritten each run)
- `web/` static UI
- `scripts/update_menus.sh` cron-friendly runner

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 scraper/update_menus.py
```

Then run a static server from repo root:

```bash
python3 -m http.server 8080
```

Open `http://localhost:8080/web/`.

## Add New Restaurant

Edit `config/restaurants.yaml` and add a new entry:

```yaml
- id: my-restaurant
  name: My Restaurant
  parser: formanka
  url: https://example.com/menu
```

Available parser values in this version:

- `formanka`
- `tradice`
- `zlatyklas`

If a new site has different HTML, add a parser function in `scraper/update_menus.py` and register it in `parsers` map.

## Cron Job

Run every 30 minutes in business hours:

```cron
*/30 7-16 * * 1-5 cd /var/www/obidek && /bin/bash scripts/update_menus.sh >> /var/log/obidek-update.log 2>&1
```

Optional safety refresh at 17:10:

```cron
10 17 * * 1-5 cd /var/www/obidek && /bin/bash scripts/update_menus.sh >> /var/log/obidek-update.log 2>&1
```


## Nginx Example

Point web root to repository folder:

```nginx
server {
  listen 80;
  server_name lunch.your-domain.tld;

  root /var/www/obidekvs;
  index web/index.html;

  location / {
    try_files $uri $uri/ /web/index.html;
  }

  location /data/ {
    add_header Cache-Control "no-store";
  }
}
```

## Notes About Menus Removed After 15:00

The scraper has a stale policy in `config/restaurants.yaml`:

```yaml
stale_policy:
  keep_last_successful: true
  hold_after_hour: 15
  max_age_hours: 36
```

If a website becomes empty/unavailable in the afternoon, last successful menu is kept (status: `stale-kept`) so your display stays useful.
