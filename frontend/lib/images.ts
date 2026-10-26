export async function compressImage(file: File): Promise<Blob> {
  if (file.size > 25_000_000)
    throw new Error("This photo is too large. Choose a smaller image.");
  const url = URL.createObjectURL(file);
  try {
    const image = new Image();
    image.src = url;
    await image.decode();
    if (Math.min(image.naturalWidth, image.naturalHeight) < 160)
      throw new Error("Use a sharper photo of at least 160 × 160 pixels.");
    const scale = Math.min(
      1,
      1920 / Math.max(image.naturalWidth, image.naturalHeight),
    );
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(image.naturalWidth * scale);
    canvas.height = Math.round(image.naturalHeight * scale);
    const ctx = canvas.getContext("2d");
    if (!ctx) throw new Error("Photo processing is unavailable.");
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.drawImage(image, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) =>
          b ? resolve(b) : reject(new Error("Could not prepare this photo.")),
        "image/jpeg",
        0.9,
      ),
    );
    if (blob.size > 8_000_000) throw new Error("Choose a smaller photo.");
    return blob;
  } catch (error) {
    throw error instanceof Error && !/decode|encoding/i.test(error.message)
      ? error
      : new Error(
          "Could not open this photo. Try a JPEG, PNG or WebP from your library.",
        );
  } finally {
    URL.revokeObjectURL(url);
  }
}
