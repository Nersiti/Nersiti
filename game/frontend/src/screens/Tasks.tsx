import { useCallback, useEffect, useState } from "react";

import { showRewardedAd } from "../ads";
import { api, ApiError } from "../api";
import { toast, toastError } from "../components/Toast";
import { compactNumber, errorText, formatDuration, formatNumber, t } from "../i18n";
import { useStore } from "../store";
import { haptic, openTgLink, shareLink } from "../tg";
import type { PlayerState, ReferralSummary, TaskInfo, TasksResponse } from "../types";

function errText(prefix: string, e: unknown): string {
  return errorText(e instanceof ApiError ? e.code : "network", prefix);
}

export default function Tasks() {
  const { setState, refresh } = useStore();
  const [data, setData] = useState<TasksResponse | null>(null);
  const [refs, setRefs] = useState<ReferralSummary | null>(null);
  const [opened, setOpened] = useState<Set<number>>(new Set());
  const [busy, setBusy] = useState<string | null>(null);

  const reload = useCallback(async () => {
    const [tasks, referrals] = await Promise.all([
      api<TasksResponse>("/tasks"),
      api<ReferralSummary>("/referrals"),
    ]);
    setData(tasks);
    setRefs(referrals);
  }, []);

  useEffect(() => {
    void reload().catch(() => toastError(null));
  }, [reload]);

  if (!data || !refs) return <div className="screen">{t("app.loading")}</div>;

  const openTask = (task: TaskInfo) => {
    if (task.url) openTgLink(task.url);
    setOpened((s) => new Set(s).add(task.id));
  };

  const checkTask = async (task: TaskInfo) => {
    setBusy(`task${task.id}`);
    try {
      const res = await api<{ reward: number; state: PlayerState }>(`/tasks/${task.id}/check`, { body: {} });
      haptic("success");
      setState(res.state);
      toast(t("tasks.reward", { n: formatNumber(res.reward) }), "success");
      await reload();
    } catch (e) {
      haptic("error");
      toast(errText("tasks.err", e), "error");
    } finally {
      setBusy(null);
    }
  };

  const claimMentor = async () => {
    setBusy("mentor");
    try {
      const res = await api<{ reward: number; state: PlayerState }>("/referrals/claim", { body: {} });
      haptic("success");
      setState(res.state);
      toast(t("ref.claimed", { n: formatNumber(res.reward) }), "success");
      await reload();
    } catch (e) {
      toast(errText("tasks.err", e), "error");
    } finally {
      setBusy(null);
    }
  };

  const watchAd = async (rewardType: "energy" | "passive" | "attack") => {
    setBusy("ad");
    try {
      const { block_id } = await api<{ block_id: string }>("/ads/intent", { body: { reward_type: rewardType } });
      const watched = await showRewardedAd(block_id);
      if (!watched) {
        toast(t("ads.failed"), "error");
        return;
      }
      haptic("success");
      toast(t("ads.pending"));
      // The ad network calls our server; the reward lands a moment later.
      setTimeout(() => void refresh().then(reload), 2500);
    } catch (e) {
      toast(e instanceof ApiError && e.code === "daily_limit" ? t("ads.limit") : errText("tasks.err", e), "error");
    } finally {
      setBusy(null);
    }
  };

  const r = refs.rewards;
  return (
    <div className="screen">
      <div className="ref-card">
        <div className="section-title">🤝 {t("ref.title")}</div>
        <p className="hint small">
          {t("ref.text", {
            invitee: compactNumber(r.invitee),
            inviter: compactNumber(r.inviter),
            premium: compactNumber(r.inviter_premium),
            level3: compactNumber(r.level3),
            share: Math.round(r.mentor_share * 100),
          })}
        </p>
        <button className="btn wide" onClick={() => shareLink(refs.link, t("ref.shareText"))}>
          {t("ref.share")}
        </button>
        <div className="ref-row">
          <span className="hint">{t("ref.count", { n: refs.count })}</span>
          <span className="grow" />
          <span className="ref-bonus">{t("ref.bonus", { n: compactNumber(refs.pending_bonus) })}</span>
          <button
            className="btn small-btn"
            disabled={busy !== null || refs.claim_in_seconds !== null || refs.pending_bonus <= 0}
            onClick={() => void claimMentor()}
          >
            {refs.claim_in_seconds !== null
              ? t("ref.claimIn", { time: formatDuration(refs.claim_in_seconds) })
              : t("ref.claim")}
          </button>
        </div>
        {refs.invitees.length > 0 && (
          <div className="invitees">
            {refs.invitees.slice(0, 10).map((f) => (
              <span key={f.id} className="chip">
                {f.is_premium ? "⭐ " : ""}
                {f.first_name} · {f.level}
              </span>
            ))}
          </div>
        )}
      </div>

      {data.ads.enabled && (
        <div className="ref-card">
          <div className="section-title">🎬 {t("ads.title")}</div>
          <p className="hint small">
            {t("ads.text", { used: data.ads.views_today, limit: data.ads.daily_limit })}
          </p>
          <div className="share-row three">
            <button className="share-btn" disabled={busy !== null} onClick={() => void watchAd("energy")}>
              {t("ads.energy")}
            </button>
            <button className="share-btn" disabled={busy !== null} onClick={() => void watchAd("passive")}>
              {t("ads.passive", { n: compactNumber(data.ads.passive_reward) })}
            </button>
            <button className="share-btn" disabled={busy !== null} onClick={() => void watchAd("attack")}>
              {t("ads.attack")}
            </button>
          </div>
        </div>
      )}

      <div className="section-title">🎯 {t("tasks.title")}</div>
      {data.tasks.length === 0 && <p className="hint">{t("tasks.empty")}</p>}
      <div className="list-plain">
        {data.tasks.map((task) => (
          <div key={task.id} className="task-row">
            <div className="grow">
              <div className="clan-row-title">{task.title}</div>
              <div className="clan-row-points small">{t("tasks.reward", { n: compactNumber(task.reward) })}</div>
            </div>
            {task.completed ? (
              <span className="hint small">{t("tasks.done")}</span>
            ) : opened.has(task.id) ? (
              <button className="btn small-btn" disabled={busy !== null} onClick={() => void checkTask(task)}>
                {t("tasks.check")}
              </button>
            ) : (
              <button className="btn small-btn" onClick={() => openTask(task)}>
                {t("tasks.go")}
              </button>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}
