/**
 * Image Processing Utilities
 * --------------------------
 * Provides client-side compression, EXIF GPS stripping, WebP capability probing,
 * long-receipt geometry preservation, single-concurrency Canvas queuing, and
 * strict iOS Safari VRAM cleanup.
 */

export type ImagePresetName =
    | "avatar"
    | "cover"
    | "spot"
    | "document"
    | "receipt"
    | "capsule"
    | "ai_input";

export interface CompressionOptions {
    maxWidth?: number;
    maxHeight?: number;
    quality?: number;
    mimeType?: string;
    preserveShortEdge?: boolean;
}

export interface ImagePresetConfig {
    maxWidth: number;
    maxHeight: number;
    quality: number;
    preserveShortEdge?: boolean;
}

export const IMAGE_PRESETS: Record<ImagePresetName, ImagePresetConfig> = {
    avatar: { maxWidth: 512, maxHeight: 512, quality: 0.82 },
    cover: { maxWidth: 1920, maxHeight: 1920, quality: 0.82 },
    spot: { maxWidth: 1600, maxHeight: 1600, quality: 0.82 },
    document: { maxWidth: 2048, maxHeight: 2048, quality: 0.85 },
    receipt: { maxWidth: 2048, maxHeight: 2048, quality: 0.85, preserveShortEdge: true },
    capsule: { maxWidth: 1600, maxHeight: 1600, quality: 0.82 },
    ai_input: { maxWidth: 1600, maxHeight: 1600, quality: 0.80, preserveShortEdge: true },
};

export const MAX_CANVAS_PIXELS = 16_000_000;
const SMALL_GIF_PASSTHROUGH_BYTES = 2 * 1024 * 1024;
const TASK_TIMEOUT_MS = 8000;
const EXIF_SLICE_BYTES = 65536;

const IMAGE_EXT_RE = /\.(jpe?g|png|webp|gif|heic|heif|bmp|avif|tiff?)$/i;
const HEIC_EXT_RE = /\.(heic|heif)$/i;
const JPEG_EXT_RE = /\.jpe?g$/i;

let cachedWebpSupport: boolean | null = null;
let compressionQueue: Promise<void> = Promise.resolve();
let taskTimeoutOverrideMs: number | null = null;

/**
 * Reset module-level singleton probe cache and serial queue state between unit tests.
 */
export function __resetImageUtilsForTesting(options?: { taskTimeoutMs?: number | null }): void {
    cachedWebpSupport = null;
    compressionQueue = Promise.resolve();
    taskTimeoutOverrideMs = options?.taskTimeoutMs ?? null;
}

/**
 * Detects whether a File is an image, including empty-MIME or octet-stream `.heic`/`.heif`
 * files produced by Windows/Android pickers. Preserves `image/svg+xml` compatibility.
 */
export function isImageFile(file: File | Blob | null | undefined): boolean {
    if (!file) return false;
    const mime = (file.type || "").trim().toLowerCase();
    if (mime.startsWith("image/")) {
        return true;
    }
    if (!mime || mime === "application/octet-stream") {
        const name = "name" in file && typeof file.name === "string" ? file.name : "";
        return IMAGE_EXT_RE.test(name);
    }
    return false;
}

export function isHeicFile(file: File | Blob | null | undefined): boolean {
    if (!file) return false;
    const mime = (file.type || "").trim().toLowerCase();
    if (mime === "image/heic" || mime === "image/heif") return true;
    const name = "name" in file && typeof file.name === "string" ? file.name : "";
    return HEIC_EXT_RE.test(name);
}

function isJpegFile(file: File | Blob | null | undefined): boolean {
    if (!file) return false;
    const mime = (file.type || "").trim().toLowerCase();
    if (mime === "image/jpeg" || mime === "image/jpg") return true;
    if (!mime || mime === "application/octet-stream") {
        const name = "name" in file && typeof file.name === "string" ? file.name : "";
        return JPEG_EXT_RE.test(name);
    }
    return false;
}

/**
 * Reads an image File/Blob as a Data URL while normalizing empty-MIME / octet-stream
 * HEIC/HEIF files to `data:image/heic;base64,...` (or `image/heif`) so backend MIME
 * allowlists and `pillow-heif` decoders accept them cleanly across Windows/Android Chrome.
 */
export function readImageFileAsDataUrl(file: File | Blob): Promise<string> {
    const normalizedMime = (file.type || "").trim().toLowerCase();
    const isHeic = isHeicFile(file);
    let targetBlob: Blob = file;
    let forcedMime: string | null = null;

    if (isHeic && (!normalizedMime || normalizedMime === "application/octet-stream")) {
        const name = "name" in file && typeof file.name === "string" ? file.name : "";
        forcedMime = /\.heif$/i.test(name) ? "image/heif" : "image/heic";
        targetBlob = new Blob([file], { type: forcedMime });
    }

    return new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onloadend = () => {
            if (typeof reader.result === "string") {
                if (forcedMime && /^data:(?:application\/octet-stream)?;/i.test(reader.result)) {
                    resolve(reader.result.replace(/^data:(?:application\/octet-stream)?;/i, `data:${forcedMime};`));
                } else {
                    resolve(reader.result);
                }
            } else {
                reject(new Error("Failed to encode image as data URL"));
            }
        };
        reader.onerror = () => reject(reader.error || new Error("FileReader error"));
        reader.readAsDataURL(targetBlob);
    });
}

/**
 * Computes target Canvas dimensions using dual-axis aspect-preserving scaling,
 * optional long-receipt short-edge preservation (bit-for-bit aligned with backend),
 * and an iOS Safari 16MP hard pixel cap. Never upscales.
 */
export function computeTargetDimensions(
    origW: number,
    origH: number,
    maxWidth: number,
    maxHeight: number,
    preserveShortEdge = false
): { width: number; height: number } {
    if (origW <= 0 || origH <= 0) {
        return { width: Math.max(1, Math.round(origW || 1)), height: Math.max(1, Math.round(origH || 1)) };
    }

    const shortEdge = Math.min(origW, origH);
    const longEdge = Math.max(origW, origH);
    const aspect = longEdge / shortEdge;

    let scale: number;
    let enforceBoxCap = true;

    if (preserveShortEdge && aspect > 2.0) {
        scale = Math.min(
            1,
            1200 / shortEdge,
            4096 / longEdge,
            Math.sqrt(5_000_000 / (origW * origH))
        );
        enforceBoxCap = false;
    } else {
        scale = Math.min(1, maxWidth / origW, maxHeight / origH);
    }

    const projectedPixels = origW * scale * (origH * scale);
    if (projectedPixels > MAX_CANVAS_PIXELS) {
        scale = Math.min(scale, Math.sqrt(MAX_CANVAS_PIXELS / (origW * origH)));
    }

    let width = Math.max(1, Math.round(origW * scale));
    let height = Math.max(1, Math.round(origH * scale));

    if (enforceBoxCap) {
        if (width > maxWidth) width = maxWidth;
        if (height > maxHeight) height = maxHeight;
    }

    if (width * height > MAX_CANVAS_PIXELS) {
        const clampScale = Math.sqrt(MAX_CANVAS_PIXELS / (width * height));
        width = Math.max(1, Math.floor(width * clampScale));
        height = Math.max(1, Math.floor(height * clampScale));
    }

    return { width, height };
}

async function readSliceBytes(blob: Blob): Promise<Uint8Array> {
    if (typeof blob.arrayBuffer === "function") {
        return new Uint8Array(await blob.arrayBuffer());
    }
    if (typeof FileReader !== "undefined") {
        return new Promise<Uint8Array>((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                if (reader.result instanceof ArrayBuffer) {
                    resolve(new Uint8Array(reader.result));
                } else {
                    resolve(new Uint8Array(0));
                }
            };
            reader.onerror = () => reject(reader.error || new Error("FileReader failed"));
            reader.readAsArrayBuffer(blob);
        });
    }
    return new Uint8Array(0);
}

/**
 * Inspects up to the first 64KB of a JPEG file by walking JPEG markers until SOS (0xFFDA)
 * to detect APP1 (0xFFE1 EXIF/XMP) or APP13 (0xFFED IPTC) metadata segments.
 * Fails closed (returns true) if the header is truncated or malformed so GPS metadata is never leaked.
 */
export async function hasJpegExifMetadata(file: Blob): Promise<boolean> {
    try {
        const slice = file.slice(0, EXIF_SLICE_BYTES);
        const bytes = await readSliceBytes(slice);
        // Fail closed if slice could not be read or does not begin with JPEG SOI (0xFF 0xD8)
        if (bytes.length < 4 || bytes[0] !== 0xff || bytes[1] !== 0xd8) {
            return true;
        }

        let offset = 2;
        while (offset < bytes.length) {
            if (bytes[offset] !== 0xff) {
                return true;
            }
            while (offset < bytes.length && bytes[offset] === 0xff) {
                offset += 1;
            }
            if (offset >= bytes.length) return true;

            const marker = bytes[offset];
            offset += 1;

            // Stuffed 0x00 byte is invalid outside entropy-coded scan data -> fail closed
            if (marker === 0x00) {
                return true;
            }

            // End of headers: SOS (0xDA) or EOI (0xD9) reached with no APP1/APP13 found
            if (marker === 0xda || marker === 0xd9) {
                return false;
            }

            // APP1 (EXIF/XMP) or APP13 (IPTC/Photoshop)
            if (marker === 0xe1 || marker === 0xed) {
                return true;
            }

            // Standalone markers without length (RST0..RST7, TEM, SOI)
            if ((marker >= 0xd0 && marker <= 0xd8) || marker === 0x01) {
                continue;
            }

            if (offset + 1 >= bytes.length) {
                return true;
            }
            const segLen = (bytes[offset] << 8) | bytes[offset + 1];
            if (segLen < 2 || offset + segLen > bytes.length) {
                return true;
            }
            offset += segLen;
        }

        // Reached EOF / 64KB boundary before encountering SOS/EOI -> fail closed
        return true;
    } catch {
        return true;
    }
}

function canvasToBlob(canvas: HTMLCanvasElement, mimeType: string, quality: number): Promise<Blob | null> {
    return new Promise((resolve) => {
        if (typeof canvas.toBlob !== "function") {
            resolve(null);
            return;
        }
        try {
            canvas.toBlob(
                (blob) => resolve(blob),
                mimeType,
                quality
            );
        } catch {
            resolve(null);
        }
    });
}

async function probeWebpSupport(): Promise<boolean> {
    if (cachedWebpSupport !== null) {
        return cachedWebpSupport;
    }
    if (typeof document === "undefined") {
        cachedWebpSupport = false;
        return false;
    }
    const probeCanvas = document.createElement("canvas");
    probeCanvas.width = 1;
    probeCanvas.height = 1;
    try {
        const ctx = probeCanvas.getContext("2d");
        if (!ctx) {
            cachedWebpSupport = false;
            return false;
        }
        ctx.fillStyle = "#ffffff";
        ctx.fillRect(0, 0, 1, 1);
        const blob = await canvasToBlob(probeCanvas, "image/webp", 0.8);
        cachedWebpSupport = Boolean(blob && blob.type === "image/webp");
        return cachedWebpSupport;
    } catch {
        cachedWebpSupport = false;
        return false;
    } finally {
        probeCanvas.width = 0;
        probeCanvas.height = 0;
    }
}

function replaceExtensionForMime(originalName: string, mimeType: string): string {
    const ext =
        mimeType === "image/webp"
            ? ".webp"
            : mimeType === "image/png"
                ? ".png"
                : ".jpg";
    const baseName = (originalName || "image").trim() || "image";
    if (/\.[a-z0-9]+$/i.test(baseName)) {
        return baseName.replace(/\.[a-z0-9]+$/i, ext);
    }
    return `${baseName}${ext}`;
}

function buildOutputFile(blob: Blob, originalFile: File, mimeType: string): File | Blob {
    const fileName = replaceExtensionForMime(originalFile.name, mimeType);
    try {
        return new File([blob], fileName, {
            type: mimeType,
            lastModified: Date.now(),
        });
    } catch {
        return blob;
    }
}

interface DecodedImage {
    source: CanvasImageSource;
    width: number;
    height: number;
    cleanup: () => void;
}

interface SerialTaskSignal {
    readonly cancelled: boolean;
    onCancel: (listener: () => void) => void;
}

function hasCanvas2dSupport(): boolean {
    if (typeof document === "undefined") {
        return false;
    }
    const probeCanvas = document.createElement("canvas");
    try {
        return Boolean(
            probeCanvas &&
            typeof probeCanvas.getContext === "function" &&
            probeCanvas.getContext("2d")
        );
    } catch {
        return false;
    } finally {
        if (probeCanvas) {
            probeCanvas.width = 0;
            probeCanvas.height = 0;
        }
    }
}

async function decodeImageSource(file: File, signal?: SerialTaskSignal): Promise<DecodedImage | null> {
    if (signal?.cancelled) {
        return null;
    }
    // 1. Prefer createImageBitmap WITHOUT resizeWidth/resizeHeight to avoid Safari EXIF rotation swap bug
    if (typeof createImageBitmap === "function") {
        try {
            const bitmap = await createImageBitmap(file);
            if (signal?.cancelled) {
                try {
                    bitmap?.close?.();
                } catch {
                    // ignore close errors
                }
                return null;
            }
            if (bitmap && bitmap.width > 0 && bitmap.height > 0) {
                return {
                    source: bitmap,
                    width: bitmap.width,
                    height: bitmap.height,
                    cleanup: () => {
                        try {
                            bitmap.close?.();
                        } catch {
                            // ignore close errors
                        }
                    },
                };
            }
            bitmap?.close?.();
        } catch {
            // Fall through to HTMLImageElement decoder
        }
    }

    if (signal?.cancelled) {
        return null;
    }

    // 2. Fallback to HTMLImageElement + Object URL (strictly guarded against missing createObjectURL)
    if (
        typeof Image === "undefined" ||
        typeof URL === "undefined" ||
        typeof URL.createObjectURL !== "function"
    ) {
        return null;
    }

    return new Promise<DecodedImage | null>((resolve) => {
        let objectUrl = "";
        let done = false;
        const img = new Image();

        const revoke = () => {
            if (!objectUrl) return;
            const toRevoke = objectUrl;
            objectUrl = "";
            try {
                URL.revokeObjectURL(toRevoke);
            } catch {
                // ignore revoke errors
            }
        };

        const finish = (result: DecodedImage | null) => {
            if (done) {
                result?.cleanup();
                return;
            }
            done = true;
            img.onload = null;
            img.onerror = null;
            resolve(result);
        };

        try {
            objectUrl = URL.createObjectURL(file);
        } catch {
            finish(null);
            return;
        }

        signal?.onCancel(() => {
            if (!done) {
                img.onload = null;
                img.onerror = null;
                img.src = "";
                revoke();
                finish(null);
            }
        });

        img.onload = () => {
            if (signal?.cancelled) {
                revoke();
                finish(null);
                return;
            }
            const w = img.naturalWidth || img.width;
            const h = img.naturalHeight || img.height;
            if (w <= 0 || h <= 0) {
                revoke();
                finish(null);
                return;
            }
            finish({
                source: img,
                width: w,
                height: h,
                cleanup: revoke,
            });
        };
        img.onerror = () => {
            revoke();
            finish(null);
        };
        img.src = objectUrl;
    });
}

function enqueueSerialTask<T>(task: (signal: SerialTaskSignal) => Promise<T>, fallback: T): Promise<T> {
    const timeoutMs = taskTimeoutOverrideMs ?? TASK_TIMEOUT_MS;

    const runWithTimeout = (): Promise<T> =>
        new Promise<T>((resolve) => {
            let settled = false;
            let isCancelled = false;
            const cancelListeners: Array<() => void> = [];
            const signal: SerialTaskSignal = {
                get cancelled() {
                    return isCancelled;
                },
                onCancel(listener: () => void) {
                    if (isCancelled) {
                        try {
                            listener();
                        } catch {
                            // ignore cancel callback errors
                        }
                    } else {
                        cancelListeners.push(listener);
                    }
                },
            };

            const timer = setTimeout(() => {
                if (!settled) {
                    settled = true;
                    isCancelled = true;
                    for (const fn of cancelListeners.splice(0)) {
                        try {
                            fn();
                        } catch {
                            // ignore cancel callback errors
                        }
                    }
                    resolve(fallback);
                }
            }, timeoutMs);

            Promise.resolve()
                .then(() => task(signal))
                .then(
                    (value) => {
                        if (!settled) {
                            settled = true;
                            clearTimeout(timer);
                            resolve(value);
                        }
                    },
                    () => {
                        if (!settled) {
                            settled = true;
                            clearTimeout(timer);
                            resolve(fallback);
                        }
                    }
                );
        });

    const previous = compressionQueue;
    let releaseNext!: () => void;
    compressionQueue = new Promise<void>((resolve) => {
        releaseNext = resolve;
    });

    return previous.then(async () => {
        try {
            return await runWithTimeout();
        } finally {
            releaseNext();
        }
    });
}

function resolveOptions(presetOrOptions: ImagePresetName | CompressionOptions): Required<Pick<CompressionOptions, "maxWidth" | "maxHeight" | "quality" | "preserveShortEdge">> & { mimeType?: string } {
    if (typeof presetOrOptions === "string") {
        const preset = IMAGE_PRESETS[presetOrOptions] ?? IMAGE_PRESETS.spot;
        return {
            maxWidth: preset.maxWidth,
            maxHeight: preset.maxHeight,
            quality: preset.quality,
            preserveShortEdge: Boolean(preset.preserveShortEdge),
        };
    }
    return {
        maxWidth: presetOrOptions.maxWidth ?? 1600,
        maxHeight: presetOrOptions.maxHeight ?? 1600,
        quality: presetOrOptions.quality ?? 0.82,
        mimeType: presetOrOptions.mimeType,
        preserveShortEdge: Boolean(presetOrOptions.preserveShortEdge),
    };
}

/**
 * Compresses an image file using a single-concurrency serial queue and Canvas API.
 * Accepts either a preset name string (e.g. `'receipt'`, `'cover'`) or custom options.
 * Fails open to the original file if decoding or 2D Canvas is unsupported (e.g. HEIC on non-Safari or jsdom).
 */
export async function compressImage(
    file: File,
    presetOrOptions: ImagePresetName | CompressionOptions = {}
): Promise<Blob | File> {
    if (!isImageFile(file)) {
        return file;
    }

    const normalizedMime = (file.type || "").trim().toLowerCase();

    // Preserve SVG exemption (F15) and small animated GIFs
    if (
        normalizedMime === "image/svg+xml" ||
        (normalizedMime === "image/gif" && file.size <= SMALL_GIF_PASSTHROUGH_BYTES)
    ) {
        return file;
    }

    // Environment pre-check: avoid deadlocks in SSR/jsdom without 2D Canvas or image decoding APIs
    const hasBitmapDecoder = typeof createImageBitmap === "function";
    const hasObjectUrlDecoder =
        typeof Image !== "undefined" &&
        typeof URL !== "undefined" &&
        typeof URL.createObjectURL === "function";
    if (
        typeof document === "undefined" ||
        (!hasBitmapDecoder && !hasObjectUrlDecoder) ||
        !hasCanvas2dSupport()
    ) {
        return file;
    }

    const opts = resolveOptions(presetOrOptions);

    return enqueueSerialTask<Blob | File>(async (signal) => {
        const decoded = await decodeImageSource(file, signal);
        if (!decoded) {
            return file;
        }
        if (signal.cancelled) {
            decoded.cleanup();
            return file;
        }

        const canvas = document.createElement("canvas");
        try {
            const { width: targetW, height: targetH } = computeTargetDimensions(
                decoded.width,
                decoded.height,
                opts.maxWidth,
                opts.maxHeight,
                opts.preserveShortEdge
            );

            canvas.width = targetW;
            canvas.height = targetH;

            const ctx = canvas.getContext("2d");
            if (!ctx || signal.cancelled) {
                return file;
            }

            // Unconditional white background fill so transparent black-text e-receipts remain legible on bg-black/95
            ctx.fillStyle = "#ffffff";
            ctx.fillRect(0, 0, targetW, targetH);
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = "high";
            ctx.drawImage(decoded.source, 0, 0, targetW, targetH);

            let desiredMime = opts.mimeType;
            if (!desiredMime) {
                desiredMime = (await probeWebpSupport()) ? "image/webp" : "image/jpeg";
            }
            if (signal.cancelled) {
                return file;
            }

            let actualMime = desiredMime;
            let outBlob = await canvasToBlob(canvas, desiredMime, opts.quality);
            if (signal.cancelled) {
                return file;
            }

            // Runtime verification: immune to iOS Safari silently returning oversized image/png for image/webp
            if (desiredMime === "image/webp" && (!outBlob || outBlob.type !== "image/webp")) {
                cachedWebpSupport = false;
                actualMime = "image/jpeg";
                outBlob = await canvasToBlob(canvas, "image/jpeg", opts.quality);
                if (signal.cancelled) {
                    return file;
                }
            }

            if (!outBlob) {
                return file;
            }

            if (outBlob.type && (outBlob.type === "image/webp" || outBlob.type === "image/jpeg" || outBlob.type === "image/png")) {
                actualMime = outBlob.type;
            }

            // Bloat & EXIF GPS stripping guard:
            // Transparent PNG / WebP / HEIC ALWAYS use Canvas white-bg output.
            // Only for JPEG when output is not smaller than input, inspect first 64KB for APP1/APP13 EXIF.
            if (outBlob.size >= file.size && isJpegFile(file)) {
                const hasExif = await hasJpegExifMetadata(file);
                if (signal.cancelled) {
                    return file;
                }
                if (!hasExif && targetW === decoded.width && targetH === decoded.height) {
                    return file;
                }
                if (hasExif) {
                    const lowerQuality = Math.max(0.6, Number((opts.quality - 0.1).toFixed(2)));
                    const retryBlob = await canvasToBlob(canvas, actualMime, lowerQuality);
                    if (signal.cancelled) {
                        return file;
                    }
                    if (
                        retryBlob &&
                        (!retryBlob.type || retryBlob.type === actualMime) &&
                        retryBlob.size < outBlob.size
                    ) {
                        outBlob = retryBlob;
                    }
                }
            }

            return buildOutputFile(outBlob, file, actualMime);
        } finally {
            decoded.cleanup();
            canvas.width = 0;
            canvas.height = 0;
        }
    }, file);
}
