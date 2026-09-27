import { useEffect, useState } from "react";

import { api } from "../api";
import { t } from "../i18n";
import { useStore } from "../store";
import { haptic, shareLink, webApp } from "../tg";
import Sheet from "./Sheet";
import { toast } from "./Toast";

interface Links {
  story_url: string;
  post_url: string;
  link: string;
  text: string;
  button: string;
}

export default function ShareSheet(props: { kind: "me" | "clan"; open: boolean; onClose: () => void }) {
  const isPremium = useStore((s) => s.state?.user.is_premium ?? false);
  const [links, setLinks] = useState<Links | null>(null);

  useEffect(() => {
    if (!props.open) return;
    api<Links>(`/share/links?kind=${props.kind}`)
      .then(setLinks)
      .catch(() => toast("network", "error"));
  }, [props.open, props.kind]);

  const toStory = () => {
    const wa = webApp();
    if (!links || !wa?.shareToStory) return toast(t("share.unavailable"));
    haptic("select");
    wa.shareToStory(links.story_url, {
      text: `${links.text} ${links.link}`,
      // Widget links are a Premium-only story feature.
      ...(isPremium ? { widget_link: { url: links.link, name: links.button } } : {}),
    });
  };

  const toChat = async () => {
    const wa = webApp();
    if (!links || !wa?.shareMessage) return toast(t("share.unavailable"));
    try {
      const { id } = await api<{ id: string }>("/share/prepare", { body: { kind: props.kind } });
      wa.shareMessage(id);
    } catch {
      toast("network", "error");
    }
  };

  return (
    <Sheet open={props.open} onClose={props.onClose}>
      <h3>{t("share.title")}</h3>
      {links && <img className="share-preview" src={new URL(links.post_url).pathname} alt="" />}
      <div className="share-actions">
        <button className="btn" onClick={toStory}>
          {t("share.story")}
        </button>
        <button className="btn" onClick={() => void toChat()}>
          {t("share.chat")}
        </button>
        <button className="btn btn-secondary" onClick={() => links && shareLink(links.link, links.text)}>
          {t("share.link")}
        </button>
      </div>
    </Sheet>
  );
}
