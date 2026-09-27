"""Load test for the World Battle API.

Requires the API to run with DEV_MODE=true (fake users via `Authorization: dev <id>`),
so run it only against a staging copy, never against production:

    pip install locust
    locust -f loadtest/locustfile.py --host http://localhost:8000 \
        --headless -u 1000 -r 50 -t 5m

Each virtual player behaves like a real one: opens the app, taps in 10-second batches,
polls the map every 15 seconds and sometimes buys upgrades, attacks or opens the
leaderboard.
"""

import itertools
import random

import h3
from locust import HttpUser, between, task

_ids = itertools.count(int(__import__("os").environ.get("LOAD_ID_START", "5000000")))
# Kazan: a real city from the generated world (run build_world first).
KAZAN = (55.78874, 49.12214)
KAZAN_CELLS = list(h3.grid_disk(h3.latlng_to_cell(*KAZAN, 6), 4))
KAZAN_CITY_ID = 551487
BBOX = "48.90,55.57,49.34,56.01"


class Player(HttpUser):
    wait_time = between(1, 3)

    def on_start(self) -> None:
        self.user_id = next(_ids)
        self.client.headers["Authorization"] = f"dev {self.user_id}"
        self.client.post("/api/session", json={}, name="/api/session")
        self.client.post(
            "/api/onboarding",
            json={"country_code": "RU", "city_id": KAZAN_CITY_ID},
            name="/api/onboarding",
        )

    @task(10)
    def tap(self) -> None:
        self.client.post("/api/tap", json={"taps": random.randint(20, 120)}, name="/api/tap")

    @task(6)
    def map_sectors(self) -> None:
        self.client.get(f"/api/map/sectors?bbox={BBOX}", name="/api/map/sectors")

    @task(2)
    def map_cities(self) -> None:
        self.client.get("/api/map/cities?bbox=30,40,60,60", name="/api/map/cities")

    @task(3)
    def attack(self) -> None:
        cell = random.choice(KAZAN_CELLS)
        with self.client.post(
            f"/api/sector/{cell}/action",
            json={"amount": random.randint(50, 300)},
            name="/api/sector/action",
            catch_response=True,
        ) as res:
            # Game rule rejections (not enough coins/power, cooldown) are expected.
            if res.status_code in (200, 400, 429):
                res.success()

    @task(2)
    def upgrades(self) -> None:
        self.client.get("/api/upgrades", name="/api/upgrades")
        with self.client.post(
            "/api/upgrades/market/buy", name="/api/upgrades/buy", catch_response=True
        ) as res:
            if res.status_code in (200, 400):
                res.success()

    @task(1)
    def leaderboard(self) -> None:
        self.client.get("/api/leaderboard/players", name="/api/leaderboard/players")
        self.client.get("/api/season", name="/api/season")

    @task(1)
    def clan(self) -> None:
        self.client.get("/api/clans/top", name="/api/clans/top")
