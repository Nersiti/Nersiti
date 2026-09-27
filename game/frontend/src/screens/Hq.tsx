import { useRef, useState, type CSSProperties, type PointerEvent } from "react";

import { api, ApiError } from "../api";
import Sheet from "../components/Sheet";
import { toast } from "../components/Toast";
import { useLiveBalance } from "../hooks";
import { compactNumber, formatNumber, t } from "../i18n";
import { useStore, withFlushedTaps } from "../store";
import { haptic } from "../tg";
import type { PlayerState } from "../types";

interface Float {
  id: number;
  x: number;
  y: number;
  n: number;
}

let floatId = 0;

export default function Hq() {
  const { state, tap, offlineEarned, dismissOffline } = useStore();
  const { coins, energy } = useLiveBalance();
  const [floats, setFloats] = useState<Float[]>([]);
  const [pressed, setPressed] = useState(false);
  const [dailyOpen, setDailyOpen] = useState(false);
  const noEnergyToastAt = useRef(0);

  if (!state) return null;

  const onTap = (e: PointerEvent<HTMLButtonElement>) => {
    e.preventDefault();
    if (!tap()) {
      haptic("error");
      if (Date.now() - noEnergyToastAt.current > 3000) {
        noEnergyToastAt.current = Date.now();
        toast(t("hq.noEnergy"));
      }
      return;
    }
    haptic("tap");
    const rect = e.currentTarget.getBoundingClientRect();
    const f = { id: ++floatId, x: e.clientX - rect.left, y: e.clientY - rect.top, n: state.tap_power };
    setFloats((list) => [...list.slice(-15), f]);
    setTimeout(() => setFloats((list) => list.filter((x) => x.id !== f.id)), 900);
  };

  const levelProgress =
    state.level_to === null ? 1 : (state.total_earned - state.level_from) / (state.level_to - state.level_from);

  return (
    <div className="screen hq">
      <header className="hq-top">
        <div className="avatar">{state.user.first_name.slice(0, 1).toUpperCase()}</div>
        <div className="grow">
          <div className="hq-name">{state.user.first_name}</div>
          <div className="hint">📍 {state.city?.name}</div>
        </div>
        <button className="daily-btn" onClick={() => setDailyOpen(true)}>
          🎁
          {!state.daily.claimed_today && <span className="dot" />}
          <span className="daily-label">{t("daily.button")}</span>
        </button>
      </header>

      <div className="stat-row">
        <Stat label={t("hq.perTap")} value={`+${state.tap_power}`} />
        <Stat
          label={t("hq.toLevel")}
          value={state.level_to === null ? t("hq.maxLevel") : compactNumber(state.level_to - state.total_earned)}
        />
        <Stat label={t("hq.perHour")} value={`+${compactNumber(state.income_per_hour)}`} />
      </div>

      <div className="coin-counter">
        <span className="coin-icon">🪙</span>
        <span>{formatNumber(coins)}</span>
      </div>

      <div className="level-line">
        <span>{t("hq.level", { n: state.level })}</span>
        <div className="progress">
          <div className="progress-fill" style={{ width: `${Math.min(100, levelProgress * 100)}%` }} />
        </div>
      </div>

      <div className="tap-area">
        <button
          className={`tap-button ${pressed ? "pressed" : ""}`}
          style={state.clan ? ({ "--clan": state.clan.color } as CSSProperties) : undefined}
          onPointerDown={(e) => {
            setPressed(true);
            onTap(e);
          }}
          onPointerUp={() => setPressed(false)}
          onPointerLeave={() => setPressed(false)}
          onContextMenu={(e) => e.preventDefault()}
        >
          <span className="tap-emblem">🌍</span>
          {floats.map((f) => (
            <span key={f.id} className="tap-float" style={{ left: f.x, top: f.y }}>
              +{f.n}
            </span>
          ))}
        </button>
      </div>

      <div className="energy">
        <span>
          ⚡ {formatNumber(energy)} / {formatNumber(state.energy_max)}
        </span>
        <div className="progress energy-bar">
          <div className="progress-fill" style={{ width: `${(energy / state.energy_max) * 100}%` }} />
        </div>
      </div>

      <Sheet open={offlineEarned > 0} onClose={dismissOffline}>
        <div className="sheet-center">
          <div className="big-emoji">💰</div>
          <h3>{t("hq.offline.title")}</h3>
          <p className="hint">{t("hq.offline.text")}</p>
          <div className="coin-counter small">
            <span className="coin-icon">🪙</span>+{formatNumber(offlineEarned)}
          </div>
          <button className="btn wide" onClick={dismissOffline}>
            {t("hq.offline.ok")}
          </button>
        </div>
      </Sheet>

      <DailySheet open={dailyOpen} onClose={() => setDailyOpen(false)} state={state} />
    </div>
  );
}

function Stat(props: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{props.label}</div>
      <div className="stat-value">{props.value}</div>
    </div>
  );
}

function DailySheet(props: { open: boolean; onClose: () => void; state: PlayerState }) {
  const setState = useStore((s) => s.setState);
  const [busy, setBusy] = useState(false);
  const { daily } = props.state;
  // Day index that will be (or was) claimed today, 1-based.
  const currentDay = daily.claimed_today ? Math.min(daily.streak, daily.rewards.length) : daily.next_day;

  const claim = async () => {
    setBusy(true);
    try {
      const res = await withFlushedTaps(() =>
        api<{ reward: number; state: PlayerState }>("/daily/claim", { body: {} }),
      );
      haptic("success");
      setState(res.state);
      toast(`+${formatNumber(res.reward)} 🪙`, "success");
    } catch (e) {
      toast(e instanceof ApiError ? e.code : "network", "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={props.open} onClose={props.onClose}>
      <h3>{t("daily.title")}</h3>
      <p className="hint">{t("daily.text")}</p>
      <div className="daily-grid">
        {daily.rewards.map((reward, i) => {
          const day = i + 1;
          const done = daily.claimed_today ? day <= currentDay : day < currentDay;
          const active = !daily.claimed_today && day === currentDay;
          return (
            <div key={day} className={`daily-cell ${done ? "done" : ""} ${active ? "active" : ""}`}>
              <div className="hint">{t("daily.day", { n: day })}</div>
              <div>🪙</div>
              <div className="daily-reward">{compactNumber(reward)}</div>
            </div>
          );
        })}
      </div>
      <button className="btn wide" disabled={busy || daily.claimed_today} onClick={() => void claim()}>
        {daily.claimed_today ? t("daily.claimed") : t("daily.claim")}
      </button>
    </Sheet>
  );
}
