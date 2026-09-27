import { useState } from "react";

import { api } from "../api";
import { toastError } from "../components/Toast";
import { compactNumber, formatNumber, t } from "../i18n";
import { useStore } from "../store";
import { haptic } from "../tg";
import type { PlayerState } from "../types";
import { flagEmoji } from "./Onboarding";

export default function Profile() {
  const { state, setState } = useStore();
  const [busy, setBusy] = useState(false);
  if (!state) return null;

  const toggleNotify = async () => {
    setBusy(true);
    try {
      const res = await api<{ state: PlayerState }>("/settings", {
        method: "PATCH",
        body: { notify_enabled: !state.notify_enabled },
      });
      haptic("select");
      setState(res.state);
    } catch {
      toastError(null);
    } finally {
      setBusy(false);
    }
  };
  const rows: [string, string][] = [
    [t("profile.level"), String(state.level)],
    [t("profile.earned"), formatNumber(state.total_earned)],
    [t("profile.country"), `${state.country_code ? flagEmoji(state.country_code) : ""} ${state.country_name ?? "—"}`],
    [t("profile.city"), state.city?.name ?? "—"],
    [t("profile.clan"), state.clan?.title ?? "—"],
    [t("hq.perHour"), `+${compactNumber(state.income_per_hour)}`],
    [t("profile.power"), `×${state.attack_mult.toFixed(2)} / ×${state.defense_mult.toFixed(2)}`],
  ];
  return (
    <div className="screen">
      <div className="profile-head">
        <div className="avatar big">{state.user.first_name.slice(0, 1).toUpperCase()}</div>
        <div>
          <div className="clan-card-title">{state.user.first_name}</div>
          {state.user.username && <div className="hint">@{state.user.username}</div>}
        </div>
      </div>
      <div className="kv">
        {rows.map(([k, v]) => (
          <div key={k} className="kv-row">
            <span className="hint">{k}</span>
            <span className="kv-value">{v}</span>
          </div>
        ))}
      </div>
      <button className="kv toggle-row" disabled={busy} onClick={() => void toggleNotify()}>
        <span className="grow">
          <span className="menu-title">🔔 {t("profile.notify")}</span>
          <span className="hint small">{t("profile.notify.hint")}</span>
        </span>
        <span className={`switch ${state.notify_enabled ? "on" : ""}`} />
      </button>
    </div>
  );
}
