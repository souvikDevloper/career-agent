
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import * as pdfjs from "pdfjs-dist";
import type { PDFDocumentProxy } from "pdfjs-dist";
pdfjs.GlobalWorkerOptions.workerSrc = "/assets/pdf.worker.min.js";
const STANDARD_FONTS = "/assets/standard_fonts/";

const PAD = 20; // space around the paper inside the scroll area
const GAP = 16; // space between pages

type Loaded = { doc: PDFDocumentProxy; aspects: number[] }; // aspect = height / width per page

function Page({ doc, num, cssWidth, renderWidth, aspect }: { doc: PDFDocumentProxy; num: number; cssWidth: number; renderWidth: number; aspect: number }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    let cancelled = false;
    let task: { cancel(): void; promise: Promise<unknown> } | null = null;
    (async () => {
      const page = await doc.getPage(num);
      const base = page.getViewport({ scale: 1 });
      const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      const viewport = page.getViewport({ scale: (renderWidth / base.width) * dpr });
      // Draw off-screen and swap in one step, so a re-render never flashes a blank page.
      const off = document.createElement("canvas");
      off.width = Math.floor(viewport.width);
      off.height = Math.floor(viewport.height);
      task = page.render({ canvasContext: off.getContext("2d")!, viewport });
      await task.promise;
      const el = ref.current;
      if (cancelled || !el) return;
      el.width = off.width;
      el.height = off.height;
      el.getContext("2d")!.drawImage(off, 0, 0);
    })().catch((e) => {
      if (e?.name !== "RenderingCancelledException") console.error("PDF page render failed", e);
    });
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [doc, num, renderWidth]);

  return (
    <canvas
      ref={ref}
      aria-label={`Resume page ${num}`}
      style={{
        display: "block",
        width: cssWidth,
        height: cssWidth * aspect,
        background: "#fff",
        borderRadius: 2,
        boxShadow: "0 1px 2px rgba(0,0,0,.5), 0 12px 40px rgba(0,0,0,.55)",
        flexShrink: 0,
      }}
    />
  );
}

export function PdfPreview({ data, zoom, fallbackUrl }: { data: Uint8Array | null; zoom: number; fallbackUrl: string | null }) {
  const scroller = useRef<HTMLDivElement>(null);
  const [loaded, setLoaded] = useState<Loaded | null>(null);
  const [failed, setFailed] = useState(false);
  const [boxWidth, setBoxWidth] = useState(0);
  const [renderBox, setRenderBox] = useState(0);
  const [current, setCurrent] = useState(1);

  // Load (or reload) the document. The previous one stays on screen until the new one is ready.
  useEffect(() => {
    if (!data) return;
    let cancelled = false;
    const task = pdfjs.getDocument({ data: data.slice(), standardFontDataUrl: STANDARD_FONTS, useSystemFonts: false }); // pdf.js takes ownership of the buffer
    task.promise
      .then(async (doc) => {
        const aspects: number[] = [];
        for (let i = 1; i <= doc.numPages; i++) {
          const v = (await doc.getPage(i)).getViewport({ scale: 1 });
          aspects.push(v.height / v.width);
        }
        if (cancelled) return void doc.destroy();
        setFailed(false);
        setLoaded((prev) => {
          prev?.doc.destroy();
          return { doc, aspects };
        });
      })
      .catch((e) => {
        if (cancelled) return;
        console.error("pdf.js could not open the preview", e);
        setFailed(true);
      });
    return () => {
      cancelled = true;
      task.destroy();
    };
  }, [data]);

  useEffect(() => () => void loaded?.doc.destroy(), []); // eslint-disable-line react-hooks/exhaustive-deps

  // Track the scroll area's width. Layout follows immediately; the sharp re-render waits for it to settle.
  useLayoutEffect(() => {
    const el = scroller.current;
    if (!el) return;
    const measure = () => setBoxWidth(el.clientWidth);
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [loaded, failed]);

  useEffect(() => {
    const t = setTimeout(() => setRenderBox(boxWidth), renderBox ? 160 : 0);
    return () => clearTimeout(t);
  }, [boxWidth]); // eslint-disable-line react-hooks/exhaustive-deps

  const fit = Math.max(0, boxWidth - PAD * 2);
  const cssWidth = Math.max(120, Math.round((fit * zoom) / 100));
  const renderWidth = renderBox ? Math.max(120, Math.round((Math.max(0, renderBox - PAD * 2) * zoom) / 100)) : cssWidth;

  function onScroll() {
    const el = scroller.current;
    if (!el || !loaded) return;
    let y = PAD;
    const mid = el.scrollTop + el.clientHeight / 2;
    let page = 1;
    loaded.aspects.forEach((a, i) => {
      const h = cssWidth * a;
      if (mid >= y) page = i + 1;
      y += h + GAP;
    });
    setCurrent(page);
  }

  if (failed && fallbackUrl) {
    return <iframe src={`${fallbackUrl}#navpanes=0&toolbar=0&view=FitH`} title="Resume Preview" style={{ width: "100%", height: "100%", border: "none", display: "block" }} />;
  }
  if (!loaded) return null;

  return (
    <div style={{ position: "relative", height: "100%" }}>
      <div ref={scroller} onScroll={onScroll} style={{ height: "100%", overflow: "auto", overscrollBehavior: "contain" }}>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: GAP, padding: PAD, width: "max-content", minWidth: "100%", boxSizing: "border-box" }}>
          {loaded.aspects.map((aspect, i) => (
            <Page key={i} doc={loaded.doc} num={i + 1} cssWidth={cssWidth} renderWidth={renderWidth} aspect={aspect} />
          ))}
        </div>
      </div>
      {loaded.aspects.length > 1 && (
        <div
          style={{
            position: "absolute",
            left: "50%",
            bottom: 14,
            transform: "translateX(-50%)",
            padding: "4px 12px",
            borderRadius: 999,
            fontSize: 12,
            color: "rgba(255,255,255,.85)",
            background: "rgba(15,17,24,.78)",
            border: "1px solid rgba(255,255,255,.12)",
            backdropFilter: "blur(8px)",
            pointerEvents: "none",
          }}
        >
          Page {current} of {loaded.aspects.length}
        </div>
      )}
    </div>
  );
}
