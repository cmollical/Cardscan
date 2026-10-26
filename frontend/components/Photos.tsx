"use client";
import { useEffect, useRef, useState } from "react";
import { Camera, ImagePlus, RefreshCw, X, Check } from "lucide-react";
import { compressImage } from "@/lib/images";
import { download } from "@/lib/api";

export function Photo({
  blob,
  id,
  alt,
  className = "",
}: {
  blob?: Blob;
  id?: string | null;
  alt: string;
  className?: string;
}) {
  const [src, setSrc] = useState("");
  useEffect(() => {
    let alive = true;
    let url = "";
    setSrc("");
    const load = async () => {
      try {
        const data = blob || (id ? await download("/media/" + id) : null);
        if (!data || !alive) return;
        url = URL.createObjectURL(data);
        setSrc(url);
      } catch {}
    };
    void load();
    return () => {
      alive = false;
      if (url) URL.revokeObjectURL(url);
    };
  }, [blob, id]);
  return src ? (
    <img className={className} src={src} alt={alt} />
  ) : (
    <span className={"photo-placeholder " + className}>
      <ImagePlus size={25} />
      <span>{alt}</span>
    </span>
  );
}

export default function Photos({
  front,
  back,
  onChange,
}: {
  front?: Blob;
  back?: Blob;
  onChange: (side: "front" | "back", blob: Blob) => Promise<void>;
}) {
  const [side, setSide] = useState<"front" | "back">("front");
  const [live, setLive] = useState(false);
  const [error, setError] = useState("");
  const [processing, setProcessing] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef<MediaStream | null>(null);
  function stop() {
    stream.current?.getTracks().forEach((track) => track.stop());
    stream.current = null;
    setLive(false);
  }
  useEffect(
    () => () => stream.current?.getTracks().forEach((track) => track.stop()),
    [],
  );
  useEffect(() => {
    if (live && video.current) {
      video.current.srcObject = stream.current;
      void video.current
        .play()
        .catch(() =>
          setError(
            "Tap the photo-library button if the camera does not start.",
          ),
        );
    }
  }, [live]);
  async function choose(file?: File) {
    if (!file) return;
    setProcessing(true);
    setError("");
    try {
      const blob = await compressImage(file);
      await onChange(side, blob);
      stop();
      if (side === "front") setSide("back");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Photo could not be saved.");
    } finally {
      setProcessing(false);
    }
  }
  async function camera() {
    setError("");
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error(
          "Live camera needs HTTPS. You can still use the camera upload or photo library.",
        );
      stream.current = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1920 },
          height: { ideal: 1920 },
        },
        audio: false,
      });
      setLive(true);
    } catch (e) {
      stop();
      setError(
        e instanceof Error && e.name === "NotAllowedError"
          ? "Camera permission was denied. Allow it in Safari settings, or choose a photo below."
          : e instanceof Error
            ? e.message
            : "Camera unavailable. Use a photo below.",
      );
    }
  }
  async function capture() {
    const v = video.current;
    if (!v?.videoWidth) return;
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    canvas.getContext("2d")?.drawImage(v, 0, 0);
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, "image/jpeg", 0.92),
    );
    if (blob)
      await choose(new File([blob], "camera.jpg", { type: "image/jpeg" }));
  }
  return (
    <section className="capture">
      <div className="segmented" aria-label="Card side">
        {(["front", "back"] as const).map((s) => (
          <button
            key={s}
            className={side === s ? "active" : ""}
            onClick={() => {
              stop();
              setSide(s);
            }}
          >
            {s === "front" ? "01 · Front" : "02 · Back"}
            {(s === "front" ? front : back) && <Check size={15} />}
          </button>
        ))}
      </div>
      <div className={"viewfinder " + (live ? "live" : "")}>
        {live ? (
          <>
            <video
              ref={video}
              autoPlay
              muted
              playsInline
              aria-label="Live camera preview"
            />
            <div className="camera-guide" />
            <button
              className="close-camera"
              aria-label="Close camera"
              onClick={stop}
            >
              <X />
            </button>
            <button
              className="shutter"
              aria-label={"Capture " + side}
              onClick={() => void capture()}
            />
          </>
        ) : (side === "front" ? front : back) ? (
          <>
            <Photo
              blob={side === "front" ? front : back}
              alt={side + " photo"}
            />
            <div className="photo-tag">
              <Check size={15} /> {side === "front" ? "Front" : "Back"} captured
            </div>
          </>
        ) : (
          <div className="capture-empty">
            <div className="card-outline">
              <span />
              <Camera size={38} />
              <span />
            </div>
            <strong>Let’s see the {side}.</strong>
            <p>
              Fill the frame. Use soft light.
              <br />
              Keep every corner visible.
            </p>
          </div>
        )}
      </div>
      {error && (
        <p className="notice error" role="alert">
          {error}
        </p>
      )}
      <button
        className="primary"
        onClick={() => void camera()}
        disabled={processing}
      >
        <Camera size={19} />
        {processing
          ? "Preparing photo…"
          : (side === "front" ? front : back)
            ? "Retake with camera"
            : "Open camera"}
      </button>
      <div className="capture-options">
        <label className="secondary file-button">
          <Camera size={17} /> Camera upload
          <input
            aria-label={"Camera upload " + side}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={(e) => {
              void choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
        <label className="secondary file-button">
          <ImagePlus size={17} /> Photo library
          <input
            aria-label={"Upload " + side}
            type="file"
            accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
            onChange={(e) => {
              void choose(e.target.files?.[0]);
              e.target.value = "";
            }}
          />
        </label>
      </div>
      <div className="photo-pair">
        {(["front", "back"] as const).map((s) => (
          <button
            key={s}
            onClick={() => {
              stop();
              setSide(s);
            }}
            aria-label={"Review " + s + " photo"}
            className={side === s ? "selected" : ""}
          >
            <Photo blob={s === "front" ? front : back} alt={s} />
            <span>
              {s === "front" ? "Front" : "Back"}
              {(s === "front" ? front : back) && <Check size={14} />}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}
