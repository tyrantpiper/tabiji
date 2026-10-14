import { compressImage } from "@/lib/image-utils"

export const MAX_PHOTO_BYTES = 8 * 1024 * 1024 // 8MB

export interface UploadProgressCallback {
    (percent: number): void
}

/**
 * Uploads a polaroid photo to Cloudinary within the tabidachi_capsules folder.
 * Enforces client-side size limits, dimension compression, and signature authentication.
 */
export async function uploadCapsulePhotoToCloudinary(
    file: File,
    onProgress?: UploadProgressCallback
): Promise<string> {
    // 🛡️ 門禁 1: 檔案大小硬性攔截 (8MB)
    if (file.size > MAX_PHOTO_BYTES) {
        throw new Error("相片大小不得超過 8MB，請重新選擇較小的相片。")
    }

    // 🛡️ 門禁 2: MIME 圖片類型驗證
    if (!file.type.startsWith("image/")) {
        throw new Error("僅支援圖片檔案格式 (JPEG, PNG, WebP, HEIC)。")
    }

    // 🛡️ 門禁 3: 前端極限壓縮至 2048px / 85% 質量 (降低傳輸流量至 ~600KB)
    const compressed = await compressImage(file, { maxWidth: 2048, maxHeight: 2048, quality: 0.85 })

    const cloudName = process.env.NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME
    const apiKey = process.env.NEXT_PUBLIC_CLOUDINARY_API_KEY
    if (!cloudName || !apiKey) {
        throw new Error("缺少 Cloudinary 環境變數 (NEXT_PUBLIC_CLOUDINARY_CLOUD_NAME / API_KEY)")
    }

    const folder = "tabidachi_capsules"
    const timestamp = Math.round(Date.now() / 1000)
    const paramsToSign = { timestamp, folder }

    // 1. 取得 Next.js 伺服器端 Cloudinary 簽名 (受白名單防禦保護)
    const signRes = await fetch("/api/sign-cloudinary", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ paramsToSign }),
    })

    if (!signRes.ok) {
        const errJson = await signRes.json().catch(() => ({}))
        throw new Error(errJson.error || `取得簽名失敗: HTTP ${signRes.status}`)
    }

    const { signature } = await signRes.json()

    // 2. 構建 FormData 直傳 Cloudinary
    const formData = new FormData()
    formData.append("file", compressed, file.name)
    formData.append("timestamp", timestamp.toString())
    formData.append("folder", folder)
    formData.append("signature", signature)
    formData.append("api_key", apiKey)

    return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest()
        xhr.open("POST", `https://api.cloudinary.com/v1_1/${cloudName}/image/upload`)

        if (xhr.upload && onProgress) {
            xhr.upload.onprogress = (event) => {
                if (event.lengthComputable) {
                    const percent = Math.round((event.loaded / event.total) * 100)
                    onProgress(percent)
                }
            }
        }

        xhr.onload = () => {
            if (xhr.status === 200) {
                try {
                    const result = JSON.parse(xhr.responseText)
                    if (result.secure_url) {
                        resolve(result.secure_url)
                    } else {
                        reject(new Error(result.error?.message || "Cloudinary 回傳無效的 secure_url"))
                    }
                } catch {
                    reject(new Error("解析 Cloudinary 回應失敗"))
                }
            } else {
                reject(new Error(`Cloudinary 上傳失敗 (HTTP ${xhr.status})`))
            }
        }

        xhr.onerror = () => reject(new Error("網路連線異常，無法連接 Cloudinary"))
        xhr.send(formData)
    })
}
