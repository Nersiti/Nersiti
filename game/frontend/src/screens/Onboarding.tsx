import { useEffect, useMemo, useState } from "react";

import { api, ApiError } from "../api";
import { compactNumber, t } from "../i18n";
import { useStore } from "../store";
import { haptic } from "../tg";
import type { CityInfo, Country, PlayerState } from "../types";

type Step = "country" | "city" | "tutorial";

export default function Onboarding() {
  const setState = useStore((s) => s.setState);
  const [step, setStep] = useState<Step>("country");
  const [countries, setCountries] = useState<Country[]>([]);
  const [country, setCountry] = useState<string | null>(null);
  const [city, setCity] = useState<CityInfo | null>(null);
  const [slide, setSlide] = useState(0);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api<{ items: Country[]; suggested: string | null }>("/countries")
      .then((res) => {
        setCountries(res.items);
        if (res.suggested && res.items.some((c) => c.code === res.suggested)) setCountry(res.suggested);
      })
      .catch(() => setError("network"));
  }, []);

  const finish = async () => {
    if (!country || !city) return;
    setSaving(true);
    setError(null);
    try {
      const res = await api<{ state: PlayerState }>("/onboarding", {
        body: { country_code: country, city_id: city.id },
      });
      haptic("success");
      setState(res.state);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "network");
      setSaving(false);
    }
  };

  if (step === "country") {
    return (
      <CountryStep
        countries={countries}
        selected={country}
        onSelect={(code) => {
          haptic("select");
          setCountry(code);
          setCity(null);
          setStep("city");
        }}
        error={error}
      />
    );
  }

  if (step === "city") {
    return (
      <CityStep
        country={country}
        onBack={() => setStep("country")}
        onSelect={(c) => {
          haptic("select");
          setCity(c);
          setStep("tutorial");
        }}
      />
    );
  }

  const slides = [
    { icon: "🪙", title: t("onb.tut1.title"), text: t("onb.tut1.text") },
    { icon: "🗺️", title: t("onb.tut2.title"), text: t("onb.tut2.text") },
    { icon: "⚔️", title: t("onb.tut3.title"), text: t("onb.tut3.text") },
  ];
  const last = slide === slides.length - 1;
  return (
    <div className="onb">
      <div className="onb-slide">
        <div className="onb-icon">{slides[slide].icon}</div>
        <h2>{slides[slide].title}</h2>
        <p>{slides[slide].text}</p>
        {city && <p className="onb-city">📍 {city.name}</p>}
      </div>
      <div className="onb-dots">
        {slides.map((_, i) => (
          <span key={i} className={i === slide ? "active" : ""} />
        ))}
      </div>
      {error && <p className="error-text">{error}</p>}
      <div className="onb-actions">
        <button className="btn btn-secondary" onClick={() => (slide ? setSlide(slide - 1) : setStep("city"))}>
          {t("onb.back")}
        </button>
        <button className="btn" disabled={saving} onClick={() => (last ? void finish() : setSlide(slide + 1))}>
          {last ? t("onb.start") : t("onb.next")}
        </button>
      </div>
    </div>
  );
}

function CountryStep(props: {
  countries: Country[];
  selected: string | null;
  onSelect: (code: string) => void;
  error: string | null;
}) {
  const [query, setQuery] = useState("");
  const list = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = q ? props.countries.filter((c) => c.name.toLowerCase().includes(q)) : props.countries;
    // Suggested country first.
    return [...filtered].sort((a, b) => Number(b.code === props.selected) - Number(a.code === props.selected));
  }, [props.countries, props.selected, query]);

  return (
    <div className="onb">
      <h2>{t("onb.country.title")}</h2>
      <p className="hint">{t("onb.country.subtitle")}</p>
      <input
        className="input"
        placeholder={t("onb.country.search")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {props.error && <p className="error-text">{props.error}</p>}
      <div className="list">
        {list.map((c) => (
          <button
            key={c.code}
            className={`list-item ${c.code === props.selected ? "selected" : ""}`}
            onClick={() => props.onSelect(c.code)}
          >
            <span className="flag">{flagEmoji(c.code)}</span>
            <span>{c.name}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

function CityStep(props: { country: string | null; onBack: () => void; onSelect: (c: CityInfo) => void }) {
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<CityInfo[] | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 2) {
      setItems(null);
      return;
    }
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ q });
      if (props.country) params.set("country", props.country);
      api<{ items: CityInfo[] }>(`/cities/search?${params}`)
        .then((res) => setItems(res.items))
        .catch(() => setItems([]));
    }, 250);
    return () => clearTimeout(timer);
  }, [query, props.country]);

  return (
    <div className="onb">
      <h2>{t("onb.city.title")}</h2>
      <p className="hint">{t("onb.city.subtitle")}</p>
      <input
        className="input"
        autoFocus
        placeholder={t("onb.city.search")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <div className="list">
        {items === null && <p className="hint">{t("onb.city.hint")}</p>}
        {items?.length === 0 && <p className="hint">{t("onb.city.empty")}</p>}
        {items?.map((c) => (
          <button key={c.id} className="list-item" onClick={() => props.onSelect(c)}>
            <span className="flag">{flagEmoji(c.country_code)}</span>
            <span className="grow">{c.name}</span>
            <span className="hint">{t("population", { n: compactNumber(c.population) })}</span>
          </button>
        ))}
      </div>
      <button className="btn btn-secondary" onClick={props.onBack}>
        {t("onb.back")}
      </button>
    </div>
  );
}

export function flagEmoji(code: string): string {
  if (!/^[A-Z]{2}$/.test(code)) return "🏳️";
  return String.fromCodePoint(...[...code].map((ch) => 0x1f1e6 + ch.charCodeAt(0) - 65));
}
