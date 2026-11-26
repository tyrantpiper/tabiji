import { notFound } from "next/navigation"
import { SplashPreviewClient } from "./splash-preview-client"

export default function SplashPreviewPage() {
    if (process.env.NODE_ENV === "production") {
        notFound()
    }
    return <SplashPreviewClient />
}
