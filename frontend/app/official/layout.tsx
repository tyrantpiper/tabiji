import type { Metadata } from "next"
import { OfficialLanguageProvider } from "@/lib/OfficialLanguageContext"

export const metadata: Metadata = {
  title: "Tabiji | 官方網站 — 自由行隨身夥伴",
  description:
    "專為自由行旅人打造的隨身行程助手。離線地圖隨開、航線行程理順與多幣別即時分帳。",
  keywords: [
    "Tabiji",
    "旅路",
    "官方網站",
    "Travel Planner",
    "自由行",
    "行程助手",
    "PWA",
    "Offline First",
    "Multi-Currency Ledger",
    "Spatial Route",
  ],
  authors: [{ name: "Ryan Su" }],
  alternates: {
    canonical: "/official",
  },
  openGraph: {
    title: "Tabiji | 官方網站 — 自由行隨身夥伴",
    description: "離線地圖隨開、航線行程理順與多幣別即時分帳。",
    url: "/official",
    siteName: "Tabiji",
    images: [
      {
        url: "/images/tabiji-art-mask.png",
        width: 1200,
        height: 630,
        alt: "Tabiji Official Portal",
      },
    ],
    locale: "zh_TW",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Tabiji | 官方網站 — 自由行隨身夥伴",
    description: "專為自由行旅人打造的隨身行程助手。",
    images: ["/images/tabiji-art-mask.png"],
  },
  robots: {
    index: true,
    follow: true,
  },
}

export default function OfficialLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <OfficialLanguageProvider>
      <link
        rel="preload"
        href="/images/tabiji-person-outline.png?v=3"
        as="image"
        type="image/png"
      />
      <link
        rel="preload"
        href="/images/tabiji-cursive-logo.png"
        as="image"
        type="image/png"
      />
      <div className="relative min-h-screen w-full overflow-x-hidden bg-[#F6F5EE] text-[#1E2927] transition-colors duration-300 antialiased selection:bg-[#0B3026] selection:text-white dark:bg-[#121A18] dark:text-[#E5EBEA] dark:selection:bg-emerald-500 dark:selection:text-stone-950">
        {children}
      </div>
    </OfficialLanguageProvider>
  )
}
