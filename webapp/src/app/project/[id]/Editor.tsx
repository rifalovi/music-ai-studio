"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createClient } from "@/lib/supabase/client";
import type { Track } from "@/lib/types";

type Props = {
  projectId: string;
  userId: string;
  initialTracks: Track[];
  engineUrl: string;
};

// --- helpers Web Audio (indépendants de React) -----------------------------
function encodeWav(buf: AudioBuffer): Blob {
  const nCh = buf.numberOfChannels,
    len = buf.length,
    sr = buf.sampleRate;
  const view = new DataView(new ArrayBuffer(44 + len * nCh * 2));
  const wr = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) view.setUint8(o + i, s.charCodeAt(i));
  };
  wr(0, "RIFF");
  view.setUint32(4, 36 + len * nCh * 2, true);
  wr(8, "WAVE");
  wr(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, nCh, true);
  view.setUint32(24, sr, true);
  view.setUint32(28, sr * nCh * 2, true);
  view.setUint16(32, nCh * 2, true);
  view.setUint16(34, 16, true);
  wr(36, "data");
  view.setUint32(40, len * nCh * 2, true);
  let o = 44;
  for (let i = 0; i < len; i++)
    for (let c = 0; c < nCh; c++) {
      const s = Math.max(-1, Math.min(1, buf.getChannelData(c)[i]));
      view.setInt16(o, s < 0 ? s * 0x8000 : s * 0x7fff, true);
      o += 2;
    }
  return new Blob([view], { type: "audio/wav" });
}

export default function Editor({ projectId, userId, initialTracks, engineUrl }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const ctxRef = useRef<AudioContext | null>(null);
  const bufRef = useRef<AudioBuffer | null>(null);
  const clipRef = useRef<AudioBuffer | null>(null);
  const undoRef = useRef<AudioBuffer[]>([]);
  const redoRef = useRef<AudioBuffer[]>([]);
  const selRef = useRef({ start: 0, end: 0 });
  const headRef = useRef(0);
  const ppsRef = useRef(120);
  const srcRef = useRef<AudioBufferSourceNode | null>(null);
  const playRef = useRef({ playing: false, ctxStart: 0, offset: 0 });

  const [status, setStatus] = useState("");
  const [hasBuf, setHasBuf] = useState(false);
  const [hasSel, setHasSel] = useState(false);
  const [busy, setBusy] = useState(false);

  const supabase = createClient();
  const ac = () => (ctxRef.current ??= new AudioContext());

  const css = (v: string) =>
    getComputedStyle(document.documentElement).getPropertyValue(v).trim();

  // --- rendu ---------------------------------------------------------------
  const draw = useCallback(() => {
    const canvas = canvasRef.current,
      buf = bufRef.current;
    if (!canvas || !buf) return;
    const g = canvas.getContext("2d")!;
    const w = parseInt(canvas.style.width),
      h = parseInt(canvas.style.height);
    g.clearRect(0, 0, w, h);
    const sel = selRef.current;
    if (sel.end > sel.start) {
      g.fillStyle = "rgba(55,208,186,.18)";
      g.fillRect(sel.start * ppsRef.current, 0, (sel.end - sel.start) * ppsRef.current, h);
    }
    const data = buf.getChannelData(0),
      mid = h / 2,
      spp = data.length / w;
    g.strokeStyle = css("--signal");
    g.beginPath();
    for (let x = 0; x < w; x++) {
      let mn = 1,
        mx = -1;
      const s = Math.floor(x * spp),
        e = Math.floor((x + 1) * spp);
      for (let i = s; i < e; i++) {
        const v = data[i];
        if (v < mn) mn = v;
        if (v > mx) mx = v;
      }
      g.moveTo(x, mid - mx * mid * 0.95);
      g.lineTo(x, mid - mn * mid * 0.95);
    }
    g.stroke();
    g.strokeStyle = css("--warm");
    g.beginPath();
    g.moveTo(headRef.current * ppsRef.current, 0);
    g.lineTo(headRef.current * ppsRef.current, h);
    g.stroke();
  }, []);

  const layout = useCallback(() => {
    const canvas = canvasRef.current,
      wrap = wrapRef.current,
      buf = bufRef.current;
    if (!canvas || !wrap || !buf) return;
    const w = Math.max(wrap.clientWidth, Math.ceil(buf.duration * ppsRef.current));
    const h = wrap.clientHeight,
      dpr = window.devicePixelRatio || 1;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.width = w + "px";
    canvas.style.height = h + "px";
    canvas.getContext("2d")!.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }, [draw]);

  const setBuffer = useCallback(
    (buf: AudioBuffer, pushUndo = true) => {
      if (pushUndo && bufRef.current) {
        undoRef.current.push(bufRef.current);
        if (undoRef.current.length > 25) undoRef.current.shift();
        redoRef.current = [];
      }
      bufRef.current = buf;
      selRef.current = { start: 0, end: 0 };
      setHasBuf(true);
      setHasSel(false);
      layout();
    },
    [layout],
  );

  // --- buffers -------------------------------------------------------------
  const mk = (ch: number, len: number, sr: number) =>
    ac().createBuffer(ch, Math.max(1, len), sr);

  const slice = (buf: AudioBuffer, from: number, to: number) => {
    const sr = buf.sampleRate,
      a = Math.max(0, Math.floor(from * sr)),
      b = Math.min(buf.length, Math.floor(to * sr));
    const out = mk(buf.numberOfChannels, Math.max(0, b - a), sr);
    for (let c = 0; c < buf.numberOfChannels; c++)
      out.getChannelData(c).set(buf.getChannelData(c).subarray(a, b));
    return out;
  };
  const removeRange = (buf: AudioBuffer, from: number, to: number) => {
    const sr = buf.sampleRate,
      a = Math.max(0, Math.floor(from * sr)),
      b = Math.min(buf.length, Math.floor(to * sr));
    const out = mk(buf.numberOfChannels, buf.length - (b - a), sr);
    for (let c = 0; c < buf.numberOfChannels; c++) {
      const src = buf.getChannelData(c),
        dst = out.getChannelData(c);
      dst.set(src.subarray(0, a), 0);
      dst.set(src.subarray(b), a);
    }
    return out;
  };
  const insertBuf = (buf: AudioBuffer, at: number, clip: AudioBuffer) => {
    const sr = buf.sampleRate,
      pos = Math.max(0, Math.min(buf.length, Math.floor(at * sr)));
    const ch = Math.max(buf.numberOfChannels, clip.numberOfChannels);
    const out = mk(ch, buf.length + clip.length, sr);
    for (let c = 0; c < ch; c++) {
      const src = buf.getChannelData(Math.min(c, buf.numberOfChannels - 1));
      const cl = clip.getChannelData(Math.min(c, clip.numberOfChannels - 1));
      const dst = out.getChannelData(c);
      dst.set(src.subarray(0, pos), 0);
      dst.set(cl, pos);
      dst.set(src.subarray(pos), pos + clip.length);
    }
    return out;
  };
  const fade = (buf: AudioBuffer, from: number, to: number, dir: number) => {
    const sr = buf.sampleRate,
      a = Math.max(0, Math.floor(from * sr)),
      b = Math.min(buf.length, Math.floor(to * sr)),
      n = b - a;
    const out = mk(buf.numberOfChannels, buf.length, sr);
    for (let c = 0; c < buf.numberOfChannels; c++) {
      const src = buf.getChannelData(c),
        dst = out.getChannelData(c);
      dst.set(src);
      for (let i = 0; i < n; i++) dst[a + i] = src[a + i] * (dir > 0 ? i / n : 1 - i / n);
    }
    return out;
  };

  // --- transport -----------------------------------------------------------
  const stop = useCallback(() => {
    const s = srcRef.current;
    if (s) {
      s.onended = null;
      try {
        s.stop();
      } catch {}
    }
    playRef.current.playing = false;
    headRef.current = selRef.current.end > selRef.current.start ? selRef.current.start : 0;
    draw();
  }, [draw]);

  const tick = useCallback(() => {
    const p = playRef.current,
      buf = bufRef.current;
    if (!p.playing || !buf) return;
    headRef.current = Math.min(buf.duration, p.offset + (ac().currentTime - p.ctxStart));
    draw();
    requestAnimationFrame(tick);
  }, [draw]);

  const play = useCallback(() => {
    const buf = bufRef.current;
    if (!buf || playRef.current.playing) return;
    const s = ac().createBufferSource();
    s.buffer = buf;
    s.connect(ac().destination);
    const sel = selRef.current;
    const off = (sel.end > sel.start ? sel.start : headRef.current) % buf.duration;
    playRef.current = { playing: true, ctxStart: ac().currentTime, offset: off };
    srcRef.current = s;
    s.start(0, off);
    s.onended = () => {
      if (playRef.current.playing) stop();
    };
    ac().resume();
    tick();
  }, [stop, tick]);

  // --- édition -------------------------------------------------------------
  const withSel = (fn: (buf: AudioBuffer, a: number, b: number) => AudioBuffer) => {
    const buf = bufRef.current,
      sel = selRef.current;
    if (!buf || sel.end <= sel.start) return;
    setBuffer(fn(buf, sel.start, sel.end));
  };
  const cut = () => withSel(removeRange);
  const trim = () => withSel(slice);
  const copy = () => {
    const buf = bufRef.current,
      sel = selRef.current;
    if (buf && sel.end > sel.start) {
      clipRef.current = slice(buf, sel.start, sel.end);
      setStatus("Sélection copiée");
    }
  };
  const paste = () => {
    const buf = bufRef.current;
    if (buf && clipRef.current) setBuffer(insertBuf(buf, headRef.current, clipRef.current));
  };
  const fadeIn = () => withSel((b, a, c) => fade(b, a, c, 1));
  const fadeOut = () => withSel((b, a, c) => fade(b, a, c, -1));
  const undo = () => {
    if (undoRef.current.length && bufRef.current) {
      redoRef.current.push(bufRef.current);
      setBuffer(undoRef.current.pop()!, false);
    }
  };
  const redo = () => {
    if (redoRef.current.length && bufRef.current) {
      undoRef.current.push(bufRef.current);
      setBuffer(redoRef.current.pop()!, false);
    }
  };

  // --- souris --------------------------------------------------------------
  const dragRef = useRef(false);
  const onDown = (e: React.MouseEvent) => {
    if (!bufRef.current) return;
    dragRef.current = true;
    const x = e.nativeEvent.offsetX / ppsRef.current;
    selRef.current = { start: x, end: x };
    headRef.current = x;
    draw();
  };
  const onMove = (e: React.MouseEvent) => {
    if (!dragRef.current || !bufRef.current) return;
    selRef.current.end = Math.max(0, Math.min(bufRef.current.duration, e.nativeEvent.offsetX / ppsRef.current));
    draw();
  };
  const onUp = () => {
    if (!dragRef.current) return;
    dragRef.current = false;
    const s = selRef.current;
    if (s.end < s.start) selRef.current = { start: s.end, end: s.start };
    if (Math.abs(selRef.current.end - selRef.current.start) < 0.001)
      selRef.current.end = selRef.current.start;
    setHasSel(selRef.current.end > selRef.current.start);
  };

  // --- IO : import, cloud, IA ----------------------------------------------
  const decodeBlob = useCallback(async (blob: Blob) => {
    const arr = await blob.arrayBuffer();
    return await ac().decodeAudioData(arr);
  }, []);

  const onImport = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setStatus("Décodage…");
    try {
      const buf = await decodeBlob(f);
      undoRef.current = [];
      redoRef.current = [];
      headRef.current = 0;
      setBuffer(buf, false);
      setStatus("");
      await uploadTrack(buf, f.name.replace(/\.[^.]+$/, "") || "import", "audio");
    } catch (err) {
      setStatus("Décodage impossible : " + (err as Error).message);
    }
  };

  const uploadTrack = useCallback(
    async (buf: AudioBuffer, name: string, kind: Track["kind"]) => {
      const path = `${userId}/${projectId}/${crypto.randomUUID()}.wav`;
      const { error } = await supabase.storage.from("audio").upload(path, encodeWav(buf), {
        contentType: "audio/wav",
        upsert: false,
      });
      if (error) {
        setStatus("Upload échoué : " + error.message);
        return;
      }
      await supabase.from("tracks").insert({ project_id: projectId, name, kind, storage_path: path });
      setStatus("Enregistré dans le projet ✓");
    },
    [projectId, userId, supabase],
  );

  const saveMaster = async () => {
    if (bufRef.current) await uploadTrack(bufRef.current, "master", "master");
  };

  const aiMaster = async () => {
    const buf = bufRef.current;
    if (!buf) return;
    if (!engineUrl) {
      setStatus("Moteur IA non configuré (NEXT_PUBLIC_ENGINE_URL).");
      return;
    }
    setBusy(true);
    setStatus("Mastering IA en cours…");
    try {
      const fd = new FormData();
      fd.append("file", encodeWav(buf), "in.wav");
      fd.append("intent", "");
      fd.append("target_lufs", "-14");
      const res = await fetch(engineUrl.replace(/\/$/, "") + "/master", { method: "POST", body: fd });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      const wav = await fetch(engineUrl.replace(/\/$/, "") + data.output_url);
      const mastered = await decodeBlob(await wav.blob());
      setBuffer(mastered);
      setStatus(`Masterisé ✓  ${data.before.integrated_lufs}→${data.after.integrated_lufs} LUFS`);
    } catch (err) {
      setStatus("Moteur injoignable : " + (err as Error).message);
    } finally {
      setBusy(false);
    }
  };

  // --- chargement initial + resize -----------------------------------------
  useEffect(() => {
    const latest = [...initialTracks].reverse().find((t) => t.storage_path);
    if (latest?.storage_path) {
      setStatus("Chargement de la piste…");
      supabase.storage
        .from("audio")
        .download(latest.storage_path)
        .then(async ({ data }) => {
          if (data) {
            setBuffer(await decodeBlob(data), false);
            setStatus("");
          }
        })
        .catch(() => setStatus(""));
    }
    const onResize = () => layout();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const Btn = (p: { on: () => void; d?: boolean; label: string }) => (
    <button className="btn" onClick={p.on} disabled={p.d}>
      {p.label}
    </button>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "calc(100vh - 57px)" }}>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 6, padding: "10px 18px", borderBottom: "1px solid var(--line)", background: "var(--surface)" }}>
        <label className="btn primary" style={{ cursor: "pointer" }}>
          Importer<input type="file" accept="audio/*" onChange={onImport} style={{ display: "none" }} />
        </label>
        <Btn on={() => (playRef.current.playing ? stop() : play())} d={!hasBuf} label="▶ / ⏸" />
        <Btn on={stop} d={!hasBuf} label="■" />
        <Btn on={cut} d={!hasSel} label="Couper" />
        <Btn on={trim} d={!hasSel} label="Rogner" />
        <Btn on={copy} d={!hasSel} label="Copier" />
        <Btn on={paste} d={!hasBuf} label="Coller" />
        <Btn on={fadeIn} d={!hasSel} label="Fade in" />
        <Btn on={fadeOut} d={!hasSel} label="Fade out" />
        <Btn on={undo} d={!hasBuf} label="Annuler" />
        <Btn on={redo} d={!hasBuf} label="Rétablir" />
        <span style={{ flex: 1 }} />
        <button className="btn" onClick={saveMaster} disabled={!hasBuf}>Enregistrer</button>
        <button className="btn primary" onClick={aiMaster} disabled={!hasBuf || busy}>
          {busy ? "…" : "Masteriser (IA)"}
        </button>
      </div>

      <div ref={wrapRef} style={{ flex: 1, overflowX: "auto", overflowY: "hidden", background: "#0b0f11", position: "relative" }}>
        <canvas
          ref={canvasRef}
          onMouseDown={onDown}
          onMouseMove={onMove}
          onMouseUp={onUp}
          style={{ display: "block", height: "100%" }}
        />
        {!hasBuf && (
          <div style={{ position: "absolute", inset: 0, display: "flex", alignItems: "center", justifyContent: "center", color: "var(--faint)", pointerEvents: "none", textAlign: "center", padding: 20 }}>
            Importe un audio pour commencer. Glisse une sélection sur la forme d'onde.
          </div>
        )}
      </div>

      <div style={{ padding: "7px 18px", borderTop: "1px solid var(--line)", fontFamily: "var(--mono)", fontSize: 12, color: "var(--warm)", minHeight: 24 }}>
        {status}
      </div>
    </div>
  );
}
