import { useEffect, useState } from "react";

import { api } from "../api";
import { ClanRow } from "../components/ClanParts";
import { useNow } from "../hooks";
import { compactNumber, formatDuration, t, type I18nKey } from "../i18n";
import { useStore } from "../store";
import type { CityRow, ClanSummary, CountryRow, Leaderboard as Board, PlayerRow } from "../types";
import { flagEmoji } from "./Onboarding";

type Kind = "players" | "clans" | "countries" | "cities";
type Scope = "global" | "country" | "city";

export function SeasonBanner() {
  const { season, seasonAt } = useStore();
  const now = useNow(30_000);
  if (!season) return null;
  const left = season.seconds_left - (now - seasonAt) / 1000;
  return (
    <div className="season-banner">
      <div className="season-title">🏆 {t("season.title", { n: season.number })}</div>
      <div className="season-left">{t("season.left", { time: formatDuration(left) })}</div>
      <p className="hint small">{t("season.hint")}</p>
    </div>
  );
}

export default function Leaderboard() {
  const state = useStore((s) => s.state);
  const [kind, setKind] = useState<Kind>("players");
  const [scope, setScope] = useState<Scope>("global");
  const [players, setPlayers] = useState<Board<PlayerRow> | null>(null);
  const [clans, setClans] = useState<Board<ClanSummary> | null>(null);
  const [countries, setCountries] = useState<Board<CountryRow> | null>(null);
  const [cities, setCities] = useState<Board<CityRow> | null>(null);

  useEffect(() => {
    if (kind === "players") {
      setPlayers(null);
      void api<Board<PlayerRow>>(`/leaderboard/players?scope=${scope}`).then(setPlayers);
    } else if (kind === "clans") {
      void api<Board<ClanSummary>>("/leaderboard/clans").then(setClans);
    } else if (kind === "countries") {
      void api<Board<CountryRow>>("/leaderboard/countries").then(setCountries);
    } else {
      void api<Board<CityRow>>("/leaderboard/cities").then(setCities);
    }
  }, [kind, scope]);

  const board = { players, clans, countries, cities }[kind];

  return (
    <div className="screen">
      <SeasonBanner />
      <div className="tabs">
        {(["players", "clans", "countries", "cities"] as Kind[]).map((k) => (
          <button key={k} className={`tab ${k === kind ? "active" : ""}`} onClick={() => setKind(k)}>
            {t(`lb.${k}` as I18nKey)}
          </button>
        ))}
      </div>
      {kind === "players" && (
        <div className="segmented">
          {(["global", "country", "city"] as Scope[]).map((s) => (
            <button key={s} className={s === scope ? "active" : ""} onClick={() => setScope(s)}>
              {t(`lb.scope.${s}` as I18nKey)}
            </button>
          ))}
        </div>
      )}

      {board?.me?.rank && <div className="my-rank">{t("lb.me", { rank: board.me.rank })}</div>}
      {board && board.items.length === 0 && <p className="hint">{t("lb.empty")}</p>}

      <div className="list-plain">
        {kind === "players" &&
          players?.items.map((p, i) => (
            <Row
              key={p.id}
              index={i}
              icon={p.country_code ? flagEmoji(p.country_code) : "👤"}
              title={p.name}
              score={p.score}
              mine={p.id === state?.user.id}
            />
          ))}
        {kind === "clans" &&
          clans?.items.map((c, i) => <ClanRow key={c.id} clan={c} index={i} mine={c.id === state?.clan?.id} />)}
        {kind === "countries" &&
          countries?.items.map((c, i) => (
            <Row
              key={c.code}
              index={i}
              icon={flagEmoji(c.code)}
              title={c.name}
              score={c.score}
              mine={c.code === state?.country_code}
            />
          ))}
        {kind === "cities" &&
          cities?.items.map((c, i) => (
            <Row
              key={c.id}
              index={i}
              icon={flagEmoji(c.country_code)}
              title={c.name}
              score={c.score}
              mine={c.id === state?.city?.id}
            />
          ))}
      </div>
    </div>
  );
}

function Row(props: { index: number; icon: string; title: string; score: number; mine?: boolean }) {
  const medal = ["🥇", "🥈", "🥉"][props.index];
  return (
    <div className={`clan-row ${props.mine ? "mine" : ""}`}>
      <span className="clan-pos">{medal ?? props.index + 1}</span>
      <span className="flag">{props.icon}</span>
      <span className="grow clan-row-title">{props.title}</span>
      <span className="clan-row-points">{compactNumber(props.score)}</span>
    </div>
  );
}
