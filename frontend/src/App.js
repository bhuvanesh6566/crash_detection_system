import React, { useState, useRef, useEffect, useCallback } from "react";
import axios from "axios";
import "./App.css";

const API = "http://localhost:5000/api";

function extractYouTubeId(url) {
  const m = url.match(/(?:v=|youtu\.be\/)([\w-]{11})/);
  return m ? m[1] : null;
}

export default function App() {
  const [tab, setTab]             = useState("upload");
  const [file, setFile]           = useState(null);
  const [ytUrl, setYtUrl]         = useState("");
  const [ytError, setYtError]     = useState("");
  const [running, setRunning]     = useState(false);
  const [progress, setProgress]   = useState(0);
  const [status, setStatus]       = useState("idle");
  const [result, setResult]       = useState(null);
  const [frameNum, setFrameNum]   = useState(0);
  const [frameSrc, setFrameSrc]   = useState(null);
  const [dragOver, setDragOver]   = useState(false);

  const inputRef       = useRef();
  const esRef          = useRef(null);
  const frameTimerRef  = useRef(null);

  // Poll /api/frame while running
  const startFramePoll = useCallback(() => {
    if (frameTimerRef.current) clearInterval(frameTimerRef.current);
    frameTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API}/frame?t=${Date.now()}`);
        if (res.status === 200) {
          const blob = await res.blob();
          setFrameSrc(prev => { if (prev) URL.revokeObjectURL(prev); return URL.createObjectURL(blob); });
        }
      } catch {}
    }, 200);
  }, []);

  const stopFramePoll = useCallback(() => {
    if (frameTimerRef.current) { clearInterval(frameTimerRef.current); frameTimerRef.current = null; }
  }, []);

  useEffect(() => () => { esRef.current?.close(); stopFramePoll(); }, [stopFramePoll]);

  const startStream = useCallback(() => {
    esRef.current?.close();
    const es = new EventSource(`${API}/stream`);
    es.onmessage = (e) => {
      const d = JSON.parse(e.data);
      setProgress(d.progress);
      setStatus(d.status);
      setFrameNum(d.current_frame || 0);
      const done = !d.running && !["starting","processing"].includes(d.status);
      if (done) {
        setResult(d); setRunning(false);
        es.close(); stopFramePoll();
      }
    };
    es.onerror = () => es.close();
    esRef.current = es;
    startFramePoll();
  }, [startFramePoll, stopFramePoll]);

  const handleFile = (f) => {
    if (!f) return;
    setFile(f); setResult(null); setStatus("idle");
    setProgress(0); setFrameSrc(null); setFrameNum(0);
  };

  const handleUpload = async () => {
    if (!file) return;
    const fd = new FormData(); fd.append("video", file);
    setRunning(true); setResult(null); setProgress(0); setStatus("starting"); setFrameSrc(null);
    try { await axios.post(`${API}/upload`, fd); startStream(); }
    catch { setStatus("error"); setRunning(false); }
  };

  const handleYouTube = async () => {
    setYtError("");
    if (!ytUrl.trim()) { setYtError("Please enter a YouTube URL."); return; }
    if (!extractYouTubeId(ytUrl)) { setYtError("Invalid YouTube URL."); return; }
    setRunning(true); setResult(null); setProgress(0); setStatus("starting"); setFrameSrc(null);
    try { await axios.post(`${API}/youtube`, { url: ytUrl }); startStream(); }
    catch (err) { setYtError(err.response?.data?.error || "Failed."); setStatus("error"); setRunning(false); }
  };

  const handleReset = async () => {
    await axios.post(`${API}/reset`);
    setFile(null); setYtUrl(""); setYtError(""); setResult(null);
    setStatus("idle"); setProgress(0); setRunning(false);
    setFrameSrc(null); setFrameNum(0);
    esRef.current?.close(); stopFramePoll();
  };

  const switchTab = (t) => { if (running) return; setTab(t); handleReset(); };

  const isCrash   = result?.crash_detected;
  const mapsLink  = result ? `https://maps.google.com/?q=${result.lat},${result.lng}` : null;
  const showFrame = frameSrc && (running || result);
  const ytId      = extractYouTubeId(ytUrl);

  return (
    <div className="app">
      {/* ── Top bar ── */}
      <div className="topbar">
        <div className="topbar-left">
          <span className="logo-icon">🚨</span>
          <span className="logo-text">CrashGuard AI</span>
        </div>
        <div className="topbar-tabs">
          <button className={`topbtn ${tab === "upload" ? "active-upload" : ""}`} onClick={() => switchTab("upload")}>
            📁 Upload Video
          </button>
          <button className={`topbtn ${tab === "youtube" ? "active-yt" : ""}`} onClick={() => switchTab("youtube")}>
            ▶ YouTube Link
          </button>
        </div>
      </div>

      <div className="body">
        {/* ── Left panel ── */}
        <div className="left-panel">

          {/* Input section */}
          <div className="input-section">
            {tab === "upload" ? (
              <>
                <div
                  className={`drop-zone ${dragOver ? "drag-over" : ""} ${file ? "has-file" : ""}`}
                  onClick={() => !file && inputRef.current.click()}
                  onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
                  onDragLeave={() => setDragOver(false)}
                  onDrop={(e) => { e.preventDefault(); setDragOver(false); handleFile(e.dataTransfer.files[0]); }}
                >
                  {file ? (
                    <div className="file-selected">
                      <span className="file-icon">🎬</span>
                      <span className="file-name-text">{file.name}</span>
                      <span className="file-size">({(file.size/1024/1024).toFixed(2)} MB)</span>
                    </div>
                  ) : (
                    <div className="drop-hint">
                      <span className="drop-icon">📹</span>
                      <p>Drop video here or click to browse</p>
                      <span className="formats">MP4 · AVI · MOV · MKV</span>
                    </div>
                  )}
                </div>
                <input ref={inputRef} type="file" accept="video/*" hidden onChange={(e) => handleFile(e.target.files[0])} />
                <div className="action-row">
                  <button className="btn-analyse" onClick={handleUpload} disabled={!file || running}>
                    {running ? "⏳ Analysing…" : "🔍 Analyse Video"}
                  </button>
                  {(file || result) && <button className="btn-reset" onClick={handleReset}>↺ Reset</button>}
                </div>
              </>
            ) : (
              <>
                <div className="yt-row">
                  <input
                    className="yt-input"
                    type="text"
                    placeholder="https://www.youtube.com/watch?v=..."
                    value={ytUrl}
                    onChange={(e) => { setYtUrl(e.target.value); setYtError(""); }}
                    disabled={running}
                  />
                </div>
                {ytError && <p className="yt-error">⚠ {ytError}</p>}
                {ytId && !running && !result && (
                  <div className="yt-thumb">
                    <img src={`https://img.youtube.com/vi/${ytId}/hqdefault.jpg`} alt="thumbnail" />
                  </div>
                )}
                <div className="action-row">
                  <button className="btn-analyse btn-yt" onClick={handleYouTube} disabled={!ytUrl || running}>
                    {running ? "⏳ Analysing…" : "▶ Analyse YouTube Video"}
                  </button>
                  {(ytUrl || result) && <button className="btn-reset" onClick={handleReset}>↺ Reset</button>}
                </div>
              </>
            )}
          </div>

          {/* Progress */}
          {(running || (status !== "idle" && status !== "error")) && (
            <div className="progress-section">
              <div className="progress-header">
                <span className={`status-dot ${isCrash ? "red" : "blue"}`} />
                <span className="status-text">
                  {{ idle:"Ready", starting:"Starting…",
                     processing:"Analysing…", crash_detected:"🚨 Crash Detected!",
                     completed_no_crash:"✅ No Crash Found", error:"❌ Error" }[status] ?? status}
                </span>
                <span className="progress-pct">{progress}%</span>
              </div>
              <div className="prog-bar-bg">
                <div className={`prog-bar-fill ${isCrash ? "red" : ""}`} style={{ width: `${progress}%` }} />
              </div>
            </div>
          )}

          {/* Result */}
          {result && (
            <div className={`result-section ${isCrash ? "danger" : "safe"}`}>
              {isCrash ? (
                <>
                  <p className="result-title">🚨 Accident Detected at Frame #{result.crash_frame}</p>
                  <div className="stats-grid">
                    <div className="stat"><span>Vehicles</span><strong>{result.vehicles_detected}</strong></div>
                    <div className="stat"><span>Telegram</span><strong>{result.alert_sent ? "✅ Sent" : "⏳"}</strong></div>
                    <div className="stat"><span>Latitude</span><strong>{result.lat}</strong></div>
                    <div className="stat"><span>Longitude</span><strong>{result.lng}</strong></div>
                  </div>
                  <a href={mapsLink} target="_blank" rel="noreferrer" className="maps-btn">📍 Open Google Maps</a>
                </>
              ) : (
                <p className="result-title">✅ No crash detected in this video.</p>
              )}
            </div>
          )}
        </div>

        {/* ── Right panel — live frame viewer ── */}
        <div className="right-panel">
          {showFrame ? (
            <div className="frame-viewer">
              <img src={frameSrc} alt="live detection" className="frame-img" />
              <div className="frame-footer">
                <span className={`frame-dot ${isCrash ? "red" : "pulse"}`} />
                Frame {frameNum}
                {isCrash && <span className="crash-badge">CRASH</span>}
              </div>
            </div>
          ) : (
            <div className="frame-placeholder">
              <span className="ph-icon">🎥</span>
              <p>Live detection frames will appear here</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
