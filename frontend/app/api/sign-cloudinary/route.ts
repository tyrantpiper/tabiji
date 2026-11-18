import { v2 as cloudinary } from "cloudinary";
import { NextResponse } from "next/server";

cloudinary.config({
    cloud_name: process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME,
    api_key: process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY,
    api_secret: process.env.CLOUDINARY_API_SECRET,
});

export async function POST(request: Request) {
    const body = await request.json().catch(() => null);
    const paramsToSign = body?.paramsToSign;
    if (!paramsToSign || typeof paramsToSign !== "object" || Array.isArray(paramsToSign)) {
        return NextResponse.json({ error: "Invalid signing payload" }, { status: 400 });
    }

    const ALLOWED_PARAM_KEYS = new Set(["timestamp", "folder", "public_id"]);
    for (const key of Object.keys(paramsToSign)) {
        if (!ALLOWED_PARAM_KEYS.has(key)) {
            return NextResponse.json({ error: `Unauthorized signing parameter: ${key}` }, { status: 400 });
        }
    }

    const ALLOWED_FOLDERS = ["tabidachi_capsules", "ryan_travel", "trip_covers", "receipts"];
    const targetFolder = paramsToSign.folder;
    const isSafeFolderFormat =
        typeof targetFolder === "string" &&
        targetFolder.length > 0 &&
        targetFolder.length <= 160 &&
        /^[a-zA-Z0-9_-]+(\/[a-zA-Z0-9_-]+)*$/.test(targetFolder);
    const isValidFolder =
        isSafeFolderFormat &&
        ALLOWED_FOLDERS.some((f) => targetFolder === f || targetFolder.startsWith(f + "/"));

    if (!isValidFolder) {
        return NextResponse.json({ error: "Unauthorized upload folder" }, { status: 400 });
    }

    const rawTimestamp = paramsToSign.timestamp;
    const timestamp =
        typeof rawTimestamp === "number" || (typeof rawTimestamp === "string" && /^\d+$/.test(rawTimestamp))
            ? Number(rawTimestamp)
            : NaN;
    if (!Number.isInteger(timestamp) || timestamp <= 0) {
        return NextResponse.json({ error: "Invalid timestamp" }, { status: 400 });
    }

    const sanitizedParams: Record<string, string | number> = {
        timestamp,
        folder: targetFolder,
    };
    if (paramsToSign.public_id !== undefined) {
        if (typeof paramsToSign.public_id !== "string" || !/^[a-zA-Z0-9_-]{1,128}$/.test(paramsToSign.public_id)) {
            return NextResponse.json({ error: "Invalid public_id" }, { status: 400 });
        }
        sanitizedParams.public_id = paramsToSign.public_id;
    }

    const apiSecret = process.env.CLOUDINARY_API_SECRET;
    if (!apiSecret) {
        return NextResponse.json({ error: "CLOUDINARY_API_SECRET not configured" }, { status: 500 });
    }

    const signature = cloudinary.utils.api_sign_request(
        sanitizedParams,
        apiSecret
    );

    return NextResponse.json({ signature });
}
