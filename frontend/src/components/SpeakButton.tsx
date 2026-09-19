/**
 * Read this out.
 *
 * Amazon Polly already speaks the agent's replies, but a score explanation, a
 * cover note and a list of what an employer still wants were silent - which is
 * the content someone would most want read back while doing something else.
 * One control, wherever there is text worth hearing.
 *
 * Only one thing speaks at a time: starting here stops whatever was playing,
 * which is handled inside speak() rather than by each caller remembering to.
 */
import { useEffect, useRef, useState } from "react";
import { speak, stopSpeaking } from "../lib/voice";
import { IStop, IVolume } from "./Icons";
import { useToast } from "./ui";

export function SpeakButton({ text, label = "Read aloud", className = "btn ghost sm" }: {
  text: string;
  label?: string;
  className?: string;
}) {
  const [playing, setPlaying] = useState(false);
  const toast = useToast();
  const alive = useRef(true);

  // Leaving the page mid-sentence should stop the audio, not follow the user
  // around the app.
  useEffect(() => {
    alive.current = true;
    return () => {
      alive.current = false;
      if (playing) stopSpeaking();
    };
  }, [playing]);

  const clean = (text || "").trim();
  if (!clean) return null;

  return (
    <button
      type="button"
      className={className}
      aria-label={playing ? "Stop reading" : label}
      onClick={async () => {
        if (playing) {
          stopSpeaking();
          setPlaying(false);
          return;
        }
        try {
          await speak(
            clean.slice(0, 2500),
            () => alive.current && setPlaying(true),
            () => alive.current && setPlaying(false),
          );
        } catch (e) {
          setPlaying(false);
          toast((e as Error).message, "error");
        }
      }}
    >
      {playing ? <IStop size={14} /> : <IVolume size={14} />} {playing ? "Stop" : label}
    </button>
  );
}
