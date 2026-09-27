import { useState } from "react";

import { api, ApiError } from "../api";
import { compactNumber, t, type I18nKey } from "../i18n";
import { useStore } from "../store";
import { haptic, openTgLink } from "../tg";
import type { ClanSummary, PlayerState } from "../types";
import { toast } from "./Toast";

export function ClanEmblem(props: { clan: Pick<ClanSummary, "title" | "color" | "is_militia">; size?: number }) {
  const size = props.size ?? 48;
  const letter = props.clan.is_militia ? "🛡️" : props.clan.title.trim().slice(0, 1).toUpperCase();
  return (
    <div
      className="clan-emblem"
      style={{ width: size, height: size, fontSize: size * 0.45, background: props.clan.color }}
    >
      {letter}
    </div>
  );
}

export function kindLabel(clan: ClanSummary): string {
  return t(`clan.kind.${clan.kind}` as I18nKey);
}

export function ClanRow(props: { clan: ClanSummary; index?: number; onClick?: () => void; mine?: boolean }) {
  const { clan } = props;
  return (
    <button className={`clan-row ${props.mine ? "mine" : ""}`} onClick={props.onClick}>
      {props.index !== undefined && <span className="clan-pos">{props.index + 1}</span>}
      <ClanEmblem clan={clan} size={36} />
      <span className="grow clan-row-text">
        <span className="clan-row-title">{clan.title}</span>
        <span className="hint small">
          {kindLabel(clan)} · 👥 {compactNumber(clan.members_count)}
        </span>
      </span>
      <span className="clan-row-points">{compactNumber(clan.season_points)}</span>
    </button>
  );
}

/** Join button with subscription handling ("subscribers only" channels). */
export function JoinClanButton(props: { clan: ClanSummary; onJoined?: () => void }) {
  const setState = useStore((s) => s.setState);
  const [busy, setBusy] = useState(false);
  const [needSub, setNeedSub] = useState(false);

  const join = async () => {
    setBusy(true);
    try {
      const res = await api<{ state: PlayerState }>(`/clans/${props.clan.id}/join`, { body: {} });
      haptic("success");
      setState(res.state);
      toast(t("clan.joined", { title: props.clan.title }), "success");
      props.onJoined?.();
    } catch (e) {
      haptic("error");
      const code = e instanceof ApiError ? e.code : "network";
      if (code === "subscribe_required") setNeedSub(true);
      toast(t(`clan.err.${code}` as I18nKey), "error");
    } finally {
      setBusy(false);
    }
  };

  if (needSub && props.clan.subscribe_url) {
    return (
      <div className="row-actions">
        <button className="btn btn-secondary" onClick={() => openTgLink(props.clan.subscribe_url!)}>
          {t("clan.subscribe")}
        </button>
        <button className="btn" disabled={busy} onClick={() => void join()}>
          {t("clan.check")}
        </button>
      </div>
    );
  }

  return (
    <button className="btn wide" disabled={busy} onClick={() => void join()}>
      {t("clan.join")}
    </button>
  );
}
