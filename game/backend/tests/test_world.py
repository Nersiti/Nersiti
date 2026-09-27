import io
import zipfile

import h3

from app.game.world import CityIn, generate_sectors, guess_ru_name, ring_k
from app.models import User
from app.scripts.build_world import load_ru_names
from tests.helpers import auth, login, seed_world


def city(id_, lat, lng, pop, admin1="01", country="RU", capital=False):
    return CityIn(id_, f"C{id_}", None, country, lat, lng, pop, capital, admin1)


def test_ring_sizes_follow_population_tiers():
    assert [ring_k(p) for p in (15_000, 100_000, 500_000, 1_000_000, 5_000_000)] == [1, 2, 3, 4, 5]
    kept, sectors = generate_sectors([city(1, 10.0, 10.0, 2_000_000, capital=True)])
    assert len(sectors) == 61  # k=4
    values = sorted(s.value for s in sectors)
    assert values.count(5) == 1  # capital center
    assert values.count(2) == 6  # first ring of a millionaire city
    assert kept[0].sectors_count == 61


def test_district_in_same_region_is_merged_but_satellite_is_kept():
    big = city(1, 55.75, 37.61, 10_000_000, admin1="48")
    district = city(2, 55.70, 37.70, 200_000, admin1="48")  # inside the ring, same region
    satellite = city(3, 55.90, 37.43, 240_000, admin1="47")  # inside the ring, other region
    kept, sectors = generate_sectors([district, satellite, big])
    assert {c.id for c in kept} == {1, 3}
    assert len({s.h3 for s in sectors}) == len(sectors)
    satellite_center = h3.latlng_to_cell(55.90, 37.43, 6)
    assert next(s for s in sectors if s.h3 == satellite_center).city_id == 3


def test_same_center_cell_keeps_bigger_city():
    kept, _ = generate_sectors([city(1, 10.0, 10.0, 20_000), city(2, 10.0001, 10.0001, 50_000)])
    assert [c.id for c in kept] == [2]


def test_guess_ru_name_prefers_modern_russian_spelling():
    alts = ["Kazan", "Kazan'", "Kasan", "Казан", "Казань", "Къазан", "Қазан", "Казањ"]
    assert guess_ru_name("Kazan", alts) == "Казань"
    alts = ["Moskva", "Moscow", "Moskau", "Москва", "Москъва", "Масква", "Москох"]
    assert guess_ru_name("Moscow", alts) == "Москва"
    assert guess_ru_name("Khabarovsk", ["Khabarovsk", "Хабаровськ", "Хабаровск"]) == "Хабаровск"
    assert guess_ru_name("Paris", ["Paris", "Pariz"]) is None


def test_load_ru_names_prefers_preferred_and_skips_historic(tmp_path):
    rows = [
        "1\t100\tru\tСтароград\t0\t0\t0\t1\t\t",  # historic
        "2\t100\tru\tНовоград\t0\t0\t0\t0\t\t",
        "3\t100\tru\tНовоград-Главный\t1\t0\t0\t0\t\t",  # preferred wins
        "4\t200\ten\tOtherTown\t1\t0\t0\t0\t\t",
        "5\t300\tru\tЧужой\t1\t0\t0\t0\t\t",  # not wanted
    ]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("alternateNamesV2.txt", "\n".join(rows) + "\n")
    path = tmp_path / "alt.zip"
    path.write_bytes(buf.getvalue())
    assert load_ru_names(path, {100, 200}) == {100: "Новоград-Главный"}


async def test_city_search_ranks_by_population_and_filters_country(client, db):
    await seed_world(db)
    await login(client, 1)
    res = await client.get("/api/cities/search", params={"q": "Каз"}, headers=auth(1))
    items = res.json()["items"]
    assert [i["name"] for i in items] == ["Казань", "Казан"]
    assert items[0]["country_name"] == "Россия"

    res = await client.get(
        "/api/cities/search", params={"q": "kaz", "country": "tr"}, headers=auth(1)
    )
    assert [i["country_code"] for i in res.json()["items"]] == ["TR"]

    res = await client.get(
        "/api/cities/search", params={"q": "kaz"}, headers=auth(2, language_code="en")
    )
    assert res.status_code == 401  # no session yet


async def test_countries_list_localized_with_suggestion(client, db):
    await seed_world(db)
    await login(client, 1, language_code="en")
    body = (await client.get("/api/countries", headers=auth(1, language_code="en"))).json()
    assert body["items"] == [{"code": "RU", "name": "Russia"}, {"code": "TR", "name": "Türkiye"}]
    assert body["suggested"] == "US"


async def test_onboarding_saves_city_once(client, db):
    ids = await seed_world(db)
    first = await login(client, 1)
    assert first["state"]["onboarded"] is False

    res = await client.post(
        "/api/onboarding", json={"country_code": "ru", "city_id": ids["kazan"]}, headers=auth(1)
    )
    assert res.status_code == 200, res.text
    state = res.json()["state"]
    assert state["onboarded"] is True
    assert state["city"]["name"] == "Казань"
    assert state["country_code"] == "RU"

    again = await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": ids["moscow"]}, headers=auth(1)
    )
    assert again.status_code == 409
    await db.refresh(await db.get(User, 1))
    assert (await db.get(User, 1)).city_id == ids["kazan"]


async def test_onboarding_rejects_unknown_city_and_country(client, db):
    ids = await seed_world(db)
    await login(client, 1)
    res = await client.post(
        "/api/onboarding", json={"country_code": "RU", "city_id": 1}, headers=auth(1)
    )
    assert res.json()["detail"] == "unknown_city"
    res = await client.post(
        "/api/onboarding", json={"country_code": "ZZ", "city_id": ids["kazan"]}, headers=auth(1)
    )
    assert res.json()["detail"] == "unknown_country"
