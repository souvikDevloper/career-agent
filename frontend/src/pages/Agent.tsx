/**
 * The agent gets the landing page's sky.
 *
 * The chat was the one screen that dropped the product's visual language the
 * moment you started using it: flat panel, boxed thread, nothing of the surface
 * the landing page sells. The canvas sits fixed behind the whole view and the
 * chat floats on it, so the conversation reads as the centre of the product
 * rather than a widget bolted into a dashboard.
 */
import { Suspense, lazy } from "react";
import { Assistant } from "../components/Assistant";
import { Shell } from "../components/Shell";

const AtmosphericCanvas = lazy(() =>
  import("../components/motion/AtmosphericCanvas").then((m) => ({ default: m.AtmosphericCanvas })),
);

export function AgentPage() {
  return (
    <Shell title="Agent" fills>
      {/* Decorative only: it never takes pointer events, and the page is fully
          readable before (or without) it, so a slow or failed chunk costs nothing. */}
      <div className="agent-sky" aria-hidden="true">
        <Suspense fallback={null}>
          <AtmosphericCanvas />
        </Suspense>
      </div>
      <Assistant />
    </Shell>
  );
}
