import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "../api";
import { ClanEmblem, ClanRow, JoinClanButton, kindLabel } from "../components/ClanParts";
import Sheet from "../components/Sheet";
import { toast } from "../components/Toast";
import { compactNumber, t } from "../i18n";
import { useStore } from "../store";
import { confirmDialog, haptic, openTgLink, shareLink } from "../tg";
import type { ClanDetails, ClanSummary, PlayerState } from "../types";

export default function Clan() {
  const { state, config, setState } = useStore();
  const [mine, setMine] = useState<ClanDetails | null>(null);
  const [top, setTop] = useState<ClanSummary[]>([]);
  const [selected, setSelected] = useState<number | null>(null);
  const clanId = state?.clan?.id;

  const reload = useCallback(async () => {
    if (!clanId) return;
    const [details, list] = await Promise.all([
      api<ClanDetails>(`/clans/${clanId}`),
      api<{ items: ClanSummary[] }>("/clans/top?limit=50"),
    ]);
    setMine(details);
    setTop(list.items);
  }, [clanId]);

  useEffect(() => {
    void reload().catch(() => toast("network", "error"));
  }, [reload]);

  if (!state || !config) return null;

  const leave = async () => {
    if (!(await confirmDialog(t("clan.leaveConfirm")))) return;
    try {
      const res = await api<{ state: PlayerState }>("/clans/leave", { body: {} });
      haptic("success");
      setState(res.state);
    } catch (e) {
      toast(e instanceof ApiError ? e.code : "network", "error");
    }
  };

  return (
    <div className="screen">
      {mine && (
        <div className="clan-card" style={{ borderColor: mine.color }}>
          <div className="clan-card-head">
            <ClanEmblem clan={mine} size={56} />
            <div className="grow">
              <div className="hint small">{t("clan.yours")}</div>
              <div className="clan-card-title">{mine.title}</div>
              <div className="hint small">
                {kindLabel(mine)}
                {mine.subscribers_only ? ` · 🔒 ${t("clan.subsOnly")}` : ""}
              </div>
            </div>
          </div>
          <div className="stat-row four">
            <MiniStat label={t("clan.members")} value={compactNumber(mine.members_count)} />
            <MiniStat label={t("clan.sectors")} value={compactNumber(mine.sectors_held)} />
            <MiniStat label={t("clan.points")} value={compactNumber(mine.season_points)} />
            <MiniStat label={t("clan.rank")} value={`#${mine.rank}`} />
          </div>
          {mine.is_militia ? (
            <p className="hint small">{t("clan.militiaHint")}</p>
          ) : (
            <div className="row-actions">
              <button
                className="btn"
                onClick={() => shareLink(mine.invite_link, t("clan.inviteText", { title: mine.title }))}
              >
                {t("clan.invite")}
              </button>
              <button className="btn btn-secondary" onClick={() => void leave()}>
                {t("clan.leave")}
              </button>
            </div>
          )}
          {mine.top_members.length > 0 && (
            <>
              <div className="section-title">{t("clan.topMembers")}</div>
              <div className="members">
                {mine.top_members.slice(0, 10).map((m, i) => (
                  <div key={m.id} className={`member ${m.id === state.user.id ? "me" : ""}`}>
                    <span className="clan-pos">{i + 1}</span>
                    <span className="grow">{m.first_name}</span>
                    <span className="hint">{compactNumber(m.season_score)}</span>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}

      <div className="create-clan">
        <div className="grow">
          <div className="section-title">{t("clan.create.title")}</div>
          <p className="hint small">{t("clan.create.text")}</p>
        </div>
        <button
          className="btn"
          onClick={() => openTgLink(`https://t.me/${config.bot_username}?start=newclan`)}
        >
          {t("clan.create.button")}
        </button>
      </div>

      <div className="section-title">{t("clan.top")}</div>
      <div className="list-plain">
        {top.map((c, i) => (
          <ClanRow key={c.id} clan={c} index={i} mine={c.id === clanId} onClick={() => setSelected(c.id)} />
        ))}
      </div>

      <ClanSheet
        clanId={selected}
        onClose={() => setSelected(null)}
        onJoined={() => {
          setSelected(null);
          void reload();
        }}
      />
    </div>
  );
}

function MiniStat(props: { label: string; value: string }) {
  return (
    <div className="stat">
      <div className="stat-label">{props.label}</div>
      <div className="stat-value">{props.value}</div>
    </div>
  );
}

export function ClanSheet(props: { clanId: number | null; onClose: () => void; onJoined: () => void }) {
  const [clan, setClan] = useState<ClanDetails | null>(null);

  useEffect(() => {
    setClan(null);
    if (props.clanId === null) return;
    api<ClanDetails>(`/clans/${props.clanId}`)
      .then(setClan)
      .catch(() => toast("network", "error"));
  }, [props.clanId]);

  return (
    <Sheet open={props.clanId !== null} onClose={props.onClose}>
      {clan && (
        <>
          <div className="clan-card-head">
            <ClanEmblem clan={clan} size={56} />
            <div className="grow">
              <div className="clan-card-title">{clan.title}</div>
              <div className="hint small">
                {kindLabel(clan)}
                {clan.subscribers_only ? ` · 🔒 ${t("clan.subsOnly")}` : ""}
              </div>
            </div>
          </div>
          <div className="stat-row four">
            <MiniStat label={t("clan.members")} value={compactNumber(clan.members_count)} />
            <MiniStat label={t("clan.sectors")} value={compactNumber(clan.sectors_held)} />
            <MiniStat label={t("clan.points")} value={compactNumber(clan.season_points)} />
            <MiniStat label={t("clan.rank")} value={`#${clan.rank}`} />
          </div>
          {!clan.is_member && !clan.is_militia && <JoinClanButton clan={clan} onJoined={props.onJoined} />}
        </>
      )}
    </Sheet>
  );
}

/** Shown once after onboarding when the app was opened with a clan link. */
export function InviteSheet() {
  const { inviteClan, dismissInvite, state } = useStore();
  const open = !!inviteClan && !!state?.onboarded && state.clan?.id !== inviteClan.id;
  if (!inviteClan) return null;
  return (
    <Sheet open={open} onClose={dismissInvite}>
      <div className="sheet-center">
        <div className="hint">{t("clan.inviteSheet.title")}</div>
        <ClanEmblem clan={inviteClan} size={64} />
        <h3>{inviteClan.title}</h3>
        <div className="hint small">
          {kindLabel(inviteClan)} · 👥 {compactNumber(inviteClan.members_count)}
        </div>
        <JoinClanButton clan={inviteClan} onJoined={dismissInvite} />
        <button className="btn btn-secondary wide" onClick={dismissInvite}>
          {t("clan.inviteSheet.skip")}
        </button>
      </div>
    </Sheet>
  );
}
