import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { useLiveBalance } from "../hooks";
import { compactNumber, formatNumber, getLang, t, type I18nKey } from "../i18n";
import { purchase, shopErrorText } from "../shop";
import { useStore, withFlushedTaps } from "../store";
import { haptic } from "../tg";
import type { PlayerState, SectorActionResult, SectorDetails } from "../types";
import { ClanEmblem } from "./ClanParts";
import Sheet from "./Sheet";
import { toast } from "./Toast";

const SHARES = [0.1, 0.25, 0.5, 1];

export default function SectorSheet(props: { h3: string | null; onClose: () => void; onChanged: () => void }) {
  const setState = useStore((s) => s.setState);
  const { coins } = useLiveBalance(500);
  const [sector, setSector] = useState<SectorDetails | null>(null);
  const [share, setShare] = useState(0.25);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async (h3: string) => {
    setSector(await api<SectorDetails>(`/sector/${h3}`));
  }, []);

  useEffect(() => {
    setSector(null);
    if (props.h3) void load(props.h3).catch(() => toast("network", "error"));
  }, [props.h3, load]);

  const amount = Math.max(0, Math.floor(coins * share));

  const act = async () => {
    if (!sector || amount <= 0) return;
    setBusy(true);
    try {
      const res = await withFlushedTaps(() =>
        api<{ result: SectorActionResult; state: PlayerState }>(`/sector/${sector.h3}/action`, {
          body: { amount },
        }),
      );
      setState(res.state);
      haptic("success");
      const r = res.result;
      if (r.flipped) toast(t("sector.done.capture"), "success");
      else if (r.action === "reinforce") toast(t("sector.done.reinforce", { n: formatNumber(r.power) }), "success");
      else toast(t("sector.done.attack", { n: formatNumber(r.power) }), "success");
      props.onChanged();
      await load(sector.h3);
    } catch (e) {
      haptic("error");
      const code = e instanceof ApiError ? e.code : "network";
      const key = `sector.err.${code}` as I18nKey;
      const text = t(key);
      toast(text === key ? code : text, "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Sheet open={props.h3 !== null} onClose={props.onClose}>
      {!sector ? (
        <div className="hint">{t("app.loading")}</div>
      ) : (
        <>
          <SectorBody sector={sector} amount={amount} share={share} setShare={setShare} busy={busy} onAct={act} />
          {sector.is_own && (
            <ShieldActions
              sector={sector}
              onDone={() => {
                props.onChanged();
                void load(sector.h3);
              }}
            />
          )}
        </>
      )}
    </Sheet>
  );
}

function SectorBody(props: {
  sector: SectorDetails;
  amount: number;
  share: number;
  setShare: (v: number) => void;
  busy: boolean;
  onAct: () => void;
}) {
  const { sector, amount } = props;
  const neutral = sector.owner === null;
  const mult = sector.is_own ? sector.defense_mult : sector.attack_mult;
  let power = Math.floor(amount * mult);
  if (!sector.is_own && sector.foothold) power = Math.floor(power / sector.foothold_divisor);

  let preview: string;
  let canAct = amount >= sector.min_amount && !sector.militia_blocked;
  if (sector.is_own) {
    preview = t("sector.willHave", { n: compactNumber(sector.defense + power) });
  } else if (neutral) {
    const enough = power >= sector.capture_cost;
    canAct = canAct && enough;
    preview = enough
      ? t("sector.willCapture", { n: compactNumber(power) })
      : t("sector.need", { n: compactNumber(sector.capture_cost) });
  } else if (power > sector.defense) {
    preview = t("sector.willCapture", { n: compactNumber(power - sector.defense) });
  } else {
    preview = t("sector.willRemain", { n: compactNumber(sector.defense - power) });
  }
  const shielded = sector.shield_until !== null && !sector.is_own;
  if (shielded) canAct = false;

  const actionLabel = sector.is_own ? t("sector.reinforce") : neutral ? t("sector.capture") : t("sector.attack");

  return (
    <>
      <div className="sector-head">
        {sector.owner ? (
          <ClanEmblem clan={sector.owner} size={48} />
        ) : (
          <div className="clan-emblem neutral" style={{ width: 48, height: 48, fontSize: 22 }}>
            ⬡
          </div>
        )}
        <div className="grow">
          <div className="clan-card-title">{sector.owner ? sector.owner.title : t("sector.neutral")}</div>
          <div className="hint small">
            📍 {sector.city?.name} · ⭐ {t("sector.value", { n: sector.value })}
          </div>
        </div>
      </div>

      <div className="sector-stats">
        <div className="stat">
          <div className="stat-label">🛡 {t("sector.defense")}</div>
          <div className="stat-value">{formatNumber(sector.defense)}</div>
        </div>
        <div className="stat">
          <div className="stat-label">⚔️ {t("sector.power")}</div>
          <div className="stat-value">{formatNumber(power)}</div>
        </div>
      </div>

      {sector.shield_until && (
        <div className="notice">
          🔒{" "}
          {t("sector.shield", {
            time: new Date(sector.shield_until).toLocaleTimeString(getLang(), { hour: "2-digit", minute: "2-digit" }),
          })}
        </div>
      )}
      {sector.is_own && <div className="notice ok">✅ {t("sector.yours")}</div>}
      {sector.militia_blocked && <div className="notice warn">{t("sector.militiaBlocked")}</div>}
      {!sector.is_own && sector.foothold && (
        <div className="notice warn">{t("sector.foothold", { n: sector.foothold_divisor })}</div>
      )}

      {!sector.militia_blocked && !shielded && (
        <>
          <div className="section-title small-title">
            {t("sector.amount")}: 🪙 {formatNumber(amount)}
          </div>
          <div className="share-row">
            {SHARES.map((v) => (
              <button
                key={v}
                className={`share-btn ${props.share === v ? "active" : ""}`}
                onClick={() => {
                  haptic("select");
                  props.setShare(v);
                }}
              >
                {v * 100}%
              </button>
            ))}
          </div>
          <div className="hint">{preview}</div>
          <button
            className={`btn wide ${sector.is_own ? "" : "btn-danger"}`}
            disabled={!canAct || props.busy}
            onClick={props.onAct}
          >
            {actionLabel}
          </button>
        </>
      )}

      {sector.log.length > 0 && (
        <>
          <div className="section-title small-title">{t("sector.log")}</div>
          <div className="members">
            {sector.log.map((entry, i) => (
              <div key={i} className="member">
                <span className="log-dot" style={{ background: entry.clan?.color ?? "#888" }} />
                <span className="grow small">
                  <b>{entry.user}</b> {t(`sector.log.${entry.action}` as I18nKey)} · {entry.clan?.title}
                </span>
                <span className="hint small">{compactNumber(entry.power)}</span>
              </div>
            ))}
          </div>
        </>
      )}
    </>
  );
}

function ShieldActions(props: { sector: SectorDetails; onDone: () => void }) {
  const { state, setState } = useStore();
  const [busy, setBusy] = useState(false);
  const vip = !!state?.vip_until;

  const freeShield = async () => {
    setBusy(true);
    try {
      const res = await api<{ state: PlayerState }>("/shop/vip_shield", { body: { h3: props.sector.h3 } });
      setState(res.state);
      haptic("success");
      toast(t("sector.shield.done"), "success");
      props.onDone();
    } catch (e) {
      haptic("error");
      toast(shopErrorText(e instanceof ApiError ? e.code : "network"), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="row-actions">
      <button
        className="btn btn-secondary"
        disabled={busy}
        onClick={async () => {
          if (await purchase("shield", props.sector.h3)) setTimeout(props.onDone, 1600);
        }}
      >
        {t("sector.shield.buy")}
      </button>
      {vip && (
        <button className="btn" disabled={busy} onClick={() => void freeShield()}>
          {t("sector.shield.vip")}
        </button>
      )}
    </div>
  );
}
