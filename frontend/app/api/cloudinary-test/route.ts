import { v2 as cloudinary } from "cloudinary";
import { NextResponse } from "next/server";

export async function GET() {
    // 🛡️ Fail-Closed: 嚴禁於生產環境暴露金鑰前綴與未授權簽章端點
    if (
        process.env.NODE_ENV === "production" ||
        process.env.VERCEL_ENV === "production" ||
        process.env.ENABLE_CLOUDINARY_TEST_ROUTE !== "true"
    ) {
        return NextResponse.json({ detail: "Not Found" }, { status: 404 });
    }

    const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME;
    const apiKey = process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY;
    const apiSecret = process.env.CLOUDINARY_API_SECRET;
    if (!cloudName || !apiKey || !apiSecret) {
        return NextResponse.json({ error: "Cloudinary credentials not configured" }, { status: 500 });
    }

    // Test signature generation
    const timestamp = Math.round(Date.now() / 1000);
    const paramsToSign = { timestamp, folder: "test" };

    cloudinary.config({
        cloud_name: cloudName,
        api_key: apiKey,
        api_secret: apiSecret,
    });

    const signature = cloudinary.utils.api_sign_request(paramsToSign, apiSecret);

    return NextResponse.json({
        cloudName,
        apiKeyConfigured: true,
        apiSecretConfigured: true,
        testSignatureGenerated: Boolean(signature),
        paramsUsed: paramsToSign,
        message: "Cloudinary local dev diagnostic check passed."
    });
}
