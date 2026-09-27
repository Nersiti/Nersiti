import { compactNumber, formatNumber, t } from "../i18n";
import { useStore } from "../store";
import { flagEmoji } from "./Onboarding";

export default function Profile() {
  const state = useStore((s) => s.state);
  if (!state) return null;
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
    </div>
  );
}
