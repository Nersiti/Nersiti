// Adsgram rewarded video: https://docs.adsgram.ai
interface AdController {
  show(): Promise<{ done: boolean; description: string; state: string; error: boolean }>;
}

declare global {
  interface Window {
    Adsgram?: { init(options: { blockId: string }): AdController };
  }
}

const SDK_URL = "https://sad.adsgram.ai/js/sad.min.js";
let loading: Promise<void> | null = null;

function loadSdk(): Promise<void> {
  if (window.Adsgram) return Promise.resolve();
  loading ??= new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = SDK_URL;
    script.async = true;
    script.onload = () => resolve();
    script.onerror = () => {
      loading = null;
      reject(new Error("adsgram sdk failed to load"));
    };
    document.head.appendChild(script);
  });
  return loading;
}

/** Shows a rewarded ad. Resolves true if the user watched it to the end. */
export async function showRewardedAd(blockId: string): Promise<boolean> {
  try {
    await loadSdk();
    const result = await window.Adsgram!.init({ blockId }).show();
    return result.done;
  } catch {
    return false;
  }
}
