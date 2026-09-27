"""Builds the playable world: cities + H3 sectors.

Run once after the first deploy:
    docker compose run --rm api python -m app.scripts.build_world

City data: GeoNames cities15000 (CC BY 4.0) shipped in the `geonamescache` package.
Russian names: GeoNames alternateNamesV2 (downloaded, ~190 MB, cached in data/);
falls back to a heuristic when the download is not possible.
"""

import argparse
import asyncio
import io
import logging
import time
import urllib.request
import zipfile
from pathlib import Path

import asyncpg
import geonamescache

from app.config import get_settings
from app.game.world import CityIn, generate_sectors, guess_ru_name

log = logging.getLogger("build_world")

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
ALT_NAMES_URL = "https://download.geonames.org/export/dump/alternateNamesV2.zip"


def load_cities() -> list[CityIn]:
    gc = geonamescache.GeonamesCache(min_city_population=15000)
    raw = gc.get_cities()
    capitals = {(c["iso"], c["capital"]) for c in gc.get_countries().values() if c.get("capital")}
    cities: list[CityIn] = []
    for item in raw.values():
        if not item.get("countrycode") or not item.get("population"):
            continue
        cities.append(
            CityIn(
                id=int(item["geonameid"]),
                name_en=item["name"][:200],
                name_ru=None,
                country_code=item["countrycode"],
                lat=float(item["latitude"]),
                lng=float(item["longitude"]),
                population=int(item["population"]),
                is_capital=(item["countrycode"], item["name"]) in capitals,
                admin1=str(item.get("admin1code") or ""),
            )
        )
    # Several cities can share the capital's name: keep only the most populous one.
    best_capital: dict[str, CityIn] = {}
    for city in cities:
        if city.is_capital:
            cur = best_capital.get(city.country_code)
            if cur is None or city.population > cur.population:
                best_capital[city.country_code] = city
    for city in cities:
        city.is_capital = best_capital.get(city.country_code) is city
    return cities


def download_alt_names(target: Path) -> bool:
    if target.exists() and target.stat().st_size > 50_000_000:
        return True
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".part")
    log.info("Downloading %s ...", ALT_NAMES_URL)
    try:
        with urllib.request.urlopen(ALT_NAMES_URL, timeout=60) as resp, tmp.open("wb") as out:
            while chunk := resp.read(1 << 20):
                out.write(chunk)
    except Exception as exc:  # network policy, DNS, timeout...
        log.warning("Could not download alternate names (%s); using heuristic", exc)
        tmp.unlink(missing_ok=True)
        return False
    tmp.rename(target)
    return True


def load_ru_names(zip_path: Path, wanted: set[int]) -> dict[int, str]:
    """Picks the Russian name per geonameid: preferred > regular > short; skips
    colloquial and historic names. Columns: id, geonameid, lang, name, isPreferred,
    isShort, isColloquial, isHistoric, from, to."""
    best: dict[int, tuple[int, str]] = {}
    with zipfile.ZipFile(zip_path) as zf, zf.open("alternateNamesV2.txt") as raw:
        for line in io.TextIOWrapper(raw, encoding="utf-8"):
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 8 or parts[2] != "ru":
                continue
            gid = int(parts[1])
            if gid not in wanted or parts[6] == "1" or parts[7] == "1":
                continue
            score = 2 if parts[4] == "1" else (0 if parts[5] == "1" else 1)
            if gid not in best or score > best[gid][0]:
                best[gid] = (score, parts[3][:200])
    return {gid: name for gid, (_, name) in best.items()}


def asyncpg_dsn(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


async def write_world(cities: list[CityIn], sectors, force: bool) -> None:
    conn = await asyncpg.connect(asyncpg_dsn(get_settings().database_url))
    try:
        existing = await conn.fetchval("SELECT count(*) FROM cities")
        if existing:
            referenced = await conn.fetchval("SELECT count(*) FROM users WHERE city_id IS NOT NULL")
            if not force:
                raise SystemExit(f"World already built ({existing} cities). Use --force.")
            if referenced:
                raise SystemExit("Players already live in this world; refusing to rebuild.")
        async with conn.transaction():
            await conn.execute("DELETE FROM sectors")
            await conn.execute("DELETE FROM clans WHERE kind = 'militia'")
            await conn.execute("DELETE FROM cities")
            await conn.copy_records_to_table(
                "cities",
                columns=[
                    "id", "name_en", "name_ru", "country_code", "lat", "lng",
                    "population", "is_capital", "sectors_count",
                ],
                records=[
                    (c.id, c.name_en, c.name_ru, c.country_code, c.lat, c.lng,
                     c.population, c.is_capital, c.sectors_count)
                    for c in cities
                ],
            )  # fmt: skip
            await conn.copy_records_to_table(
                "sectors",
                columns=["h3", "city_id", "lat", "lng", "value", "defense"],
                records=[(s.h3, s.city_id, s.lat, s.lng, s.value, 0) for s in sectors],
            )
        await conn.execute("ANALYZE cities; ANALYZE sectors;")
    finally:
        await conn.close()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="rebuild an existing empty world")
    parser.add_argument(
        "--ru-names",
        choices=["auto", "geonames", "heuristic"],
        default="auto",
        help="where Russian city names come from",
    )
    args = parser.parse_args()

    started = time.monotonic()
    cities = load_cities()
    log.info("Loaded %d cities", len(cities))

    ru_names: dict[int, str] = {}
    if args.ru_names != "heuristic":
        zip_path = DATA_DIR / "alternateNamesV2.zip"
        if download_alt_names(zip_path):
            ru_names = load_ru_names(zip_path, {c.id for c in cities})
            log.info("Russian names from GeoNames: %d", len(ru_names))
        elif args.ru_names == "geonames":
            raise SystemExit("alternateNamesV2 is required but could not be downloaded")

    gc_raw = geonamescache.GeonamesCache(min_city_population=15000).get_cities()
    for city in cities:
        city.name_ru = ru_names.get(city.id) or guess_ru_name(
            city.name_en, gc_raw.get(str(city.id), {}).get("alternatenames", [])
        )

    kept, sectors = generate_sectors(cities)
    log.info("Playable cities: %d, sectors: %d", len(kept), len(sectors))
    asyncio.run(write_world(kept, sectors, args.force))
    log.info("Done in %.1fs", time.monotonic() - started)


if __name__ == "__main__":
    main()
