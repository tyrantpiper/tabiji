"use client"

import { useState, useEffect, useRef } from "react"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Label } from "@/components/ui/label"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"
import { 
    FileText, 
    Image as ImageIcon, 
    Sparkles, 
    Loader2, 
    UploadCloud, 
    X, 
    CheckCircle2
} from "lucide-react"
import { cn } from "@/lib/utils"
import { toast } from "sonner"
import { aiApi } from "@/lib/api"
import { motion, AnimatePresence } from "framer-motion"

interface AiImportTripWizardProps {
    userId: string
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onComplete: (parsedData: any) => void
}

// 經典範本快選 (亞洲、歐洲、美洲 各一，完整 5 日行程)
const TEMPLATE_PILLS_ZH = [
    {
        label: "🇯🇵 東京 5 日自由行",
        content: `# 東京 5 日自由行行程表
## Day 1 (10/01)
- 10:30 抵達 成田機場 (搭乘 Skyliner 前往市區)
- 13:00 淺草寺 (參拜與雷門拍照)
- 15:30 晴空塔 (展望台眺望與逛街)
- 18:30 淺草今半 (壽喜燒百年名店晚餐)
- 20:30 隅田川水岸步道散步

## Day 2 (10/02)
- 09:00 築地場外市場 (生魚片丼飯早餐)
- 11:30 銀座商圈 (GINZA SIX 與文房具伊東屋)
- 15:00 皇居外苑與二重橋
- 18:00 六本木之丘 (森大樓 52F 觀景台看東京鐵塔夜景)
- 20:30 六本木 一蘭拉麵

## Day 3 (10/03)
- 09:30 明治神宮 (森林散步參拜)
- 11:30 原宿竹下通與表參道 (咖啡廳跑店)
- 15:00 澀谷 SHIBUYA SKY (夕陽展望台)
- 18:30 澀谷十字路口與居酒屋街

## Day 4 (10/04)
- 09:30 上野恩賜公園 (阿美橫町漫步採買)
- 12:30 秋葉原電器街 (動漫文化巡禮與女僕咖啡)
- 15:30 東京車站丸之內 (百年紅磚車站建築美學)
- 18:30 銀座篝拉麵 (極上雞白湯拉麵晚餐)

## Day 5 (10/05)
- 10:00 台場海濱公園 (自由女神像與彩虹大橋眺望)
- 12:30 teamLab Planets (沉浸式光影藝術體感)
- 15:30 羽田機場 (市區退稅採買與搭機返程)`
    },
    {
        label: "🇫🇷 巴黎 5 日藝文浪漫",
        content: `# 巴黎 5 日藝文浪漫行程表
## Day 1 (05/10)
- 10:00 抵達 戴高樂機場 (搭乘 RER B 線前往巴黎市區)
- 14:00 艾菲爾鐵塔 (戰神廣場漫步與鐵塔合影)
- 17:00 塞納河遊船 (Bateaux Parisiens 傍晚遊船體驗)
- 19:30 夏樂宮 (觀賞鐵塔夜間整點閃燈秀)

## Day 2 (05/11)
- 09:00 羅浮宮博物館 (蒙娜麗莎與勝利女神經典巡禮)
- 13:00 杜樂麗花園 (露天綠椅漫步休閒)
- 15:00 協和廣場與香榭麗舍大道
- 18:00 巴黎凱旋門 (登頂俯瞰十二道放射大道日落)
- 20:00 香榭麗舍法式小酒館晚餐

## Day 3 (05/12)
- 09:30 奧賽美術館 (印象派梵谷與莫內名作賞析)
- 13:00 巴黎聖母院與西堤島漫步
- 15:30 莎士比亞書店 (塞納河畔左岸藝文書香)
- 18:00 拉丁區雙叟咖啡館 (享受經典左岸露天咖啡)

## Day 4 (05/13)
- 09:00 凡爾賽宮 (鏡廳與宏偉皇家法式花園半日遊)
- 14:30 瑪黑區 (歷史街區選物店與孚日廣場散策)
- 18:30 巴士底市集周邊經典油封鴨晚餐

## Day 5 (05/14)
- 09:30 蒙馬特高地與聖心堂 (俯瞰巴黎全景)
- 11:30 蒙馬特愛牆 (浪漫打卡與畫家村漫步)
- 14:00 老佛爺百貨奧斯曼旗艦店 (彩繪玻璃圓頂採買伴手禮)
- 17:30 前往 戴高樂機場 (辦理退稅手續與搭機回程)`
    },
    {
        label: "🇺🇸 紐約 5 日都會經典",
        content: `# 紐約 5 日都會經典行程表
## Day 1 (09/18)
- 11:00 抵達 甘迺迪國際機場 (搭乘 AirTrain 前往曼哈頓)
- 14:30 時代廣場 (百老匯街景與璀璨廣告看板)
- 17:30 洛克斐勒中心 (巨石陣觀景台 Top of the Rock 日落夜景)
- 20:00 Junior's Restaurant (經典紐約起司蛋糕與美式晚餐)

## Day 2 (09/19)
- 09:00 中央公園 (畢士大噴泉與林蔭大道晨間散步)
- 11:30 大都會藝術博物館 (The Met 世界級藝術殿堂)
- 15:30 第五大道 (奢華商圈與聖派翠克大教堂)
- 18:30 帝國大廈 (經典地標 86 樓露天觀景台夜景)

## Day 3 (09/20)
- 09:00 砲台公園搭乘渡輪 (參觀自由女神像與埃利斯島)
- 12:30 華爾街 (紐約證券交易所與華爾街銅牛拍照)
- 14:30 911 國家紀念博物館與世貿中心轉運站
- 17:30 雀兒喜市場 (龍蝦堡晚餐與文創市集)

## Day 4 (09/21)
- 09:30 高線公園 The High Line (空中鐵道花園漫步)
- 11:30 哈德遜園區 The Vessel 與 Edge 觀景台
- 14:30 蘇活區 SoHo (鑄鐵建築群與潮流品牌選品)
- 17:30 布魯克林大橋 (黃昏徒步橫跨東河賞曼哈頓天際線)
- 19:30 DUMBO 曼哈頓大橋網美街角拍照與 Grimaldi's Pizza

## Day 5 (09/22)
- 09:30 紐約現代藝術博物館 MoMA (星夜與現代藝術精華)
- 12:30 中央車站 Grand Central Terminal (百年天花板星空)
- 14:30 布萊恩公園與紐約公共圖書館
- 17:00 前往 甘迺迪國際機場 (搭機返程)`
    }
]

const TEMPLATE_PILLS_EN = [
    {
        label: "🇯🇵 Tokyo 5-Day Highlights",
        content: `# Tokyo 5-Day Highlights Itinerary
## Day 1 (10/01)
- 10:30 Arrive at Narita Airport (Take Skyliner to downtown)
- 13:00 Senso-ji Temple (Asakusa gate and historic walking)
- 15:30 Tokyo Skytree (Observation deck and shopping)
- 18:30 Asakusa Imahan (Traditional Sukiyaki Dinner)
- 20:30 Sumida River Waterfront Stroll

## Day 2 (10/02)
- 09:00 Tsukiji Outer Market (Fresh sashimi bowl breakfast)
- 11:30 Ginza Shopping District (GINZA SIX and Itoya)
- 15:00 Imperial Palace East Gardens and Nijubashi Bridge
- 18:00 Roppongi Hills (Mori Tower 52F Tokyo Tower night view)
- 20:30 Roppongi Ichiran Ramen

## Day 3 (10/03)
- 09:30 Meiji Shrine (Forested shrine morning walk)
- 11:30 Harajuku Takeshita Street and Omotesando Cafes
- 15:00 Shibuya SHIBUYA SKY (Sunset observation deck)
- 18:30 Shibuya Crossing and Nonbei Yokocho Izakaya

## Day 4 (10/04)
- 09:30 Ueno Onshi Park and Ameyoko Market
- 12:30 Akihabara Electric Town (Anime culture and tech)
- 15:30 Tokyo Station Marunouchi Brick Architecture
- 18:30 Ginza Kagari Ramen (Tori Paitan Ramen)

## Day 5 (10/05)
- 10:00 Odaiba Seaside Park (Statue of Liberty and Rainbow Bridge)
- 12:30 teamLab Planets (Immersive digital art experience)
- 15:30 Haneda Airport Departure`
    },
    {
        label: "🇫🇷 Paris 5-Day Cultural Romance",
        content: `# Paris 5-Day Cultural Romance Itinerary
## Day 1 (05/10)
- 10:00 Arrive at CDG Airport (Take RER B to Paris center)
- 14:00 Eiffel Tower (Champ de Mars walk and iconic photography)
- 17:00 Seine River Cruise (Bateaux Parisiens sunset cruise)
- 19:30 Trocadero Square (Eiffel Tower evening sparkle show)

## Day 2 (05/11)
- 09:00 Louvre Museum (Mona Lisa and Venus de Milo tour)
- 13:00 Tuileries Garden (Relaxing park walk)
- 15:00 Place de la Concorde and Champs-Elysees Avenue
- 18:00 Arc de Triomphe (Rooftop sunset panoramic view)
- 20:00 Classic French Bistro Dinner on Champs-Elysees

## Day 3 (05/12)
- 09:30 Musee d'Orsay (Impressionist masterpieces of Van Gogh and Monet)
- 13:00 Notre-Dame Cathedral and Ile de la Cite
- 15:30 Shakespeare and Company Bookstore (Left Bank literary walk)
- 18:00 Cafe de Flore or Les Deux Magots (Historic Left Bank coffee)

## Day 4 (05/13)
- 09:00 Palace of Versailles (Hall of Mirrors and royal gardens)
- 14:30 Le Marais District (Historic boutiques and Place des Vosges)
- 18:30 Bastille neighborhood duck confit dinner

## Day 5 (05/14)
- 09:30 Montmartre and Sacre-Coeur Basilica
- 11:30 Wall of Love (Square Jehan Rictus romance stroll)
- 14:00 Galeries Lafayette Haussmann (Art Nouveau stained-glass dome)
- 17:30 Transfer to CDG Airport for Departure`
    },
    {
        label: "🇺🇸 NYC 5-Day Urban Explorer",
        content: `# NYC 5-Day Urban Explorer Itinerary
## Day 1 (09/18)
- 11:00 Arrive at JFK Airport (AirTrain to Manhattan)
- 14:30 Times Square (Broadway neon lights and vibrant atmosphere)
- 17:30 Rockefeller Center (Top of the Rock sunset observation deck)
- 20:00 Junior's Restaurant (Classic NY cheesecake and dinner)

## Day 2 (09/19)
- 09:00 Central Park (Bethesda Terrace and The Mall morning walk)
- 11:30 The Metropolitan Museum of Art (The Met world-class exhibits)
- 15:30 Fifth Avenue (Shopping and St. Patrick's Cathedral)
- 18:30 Empire State Building (86th floor open-air observatory night view)

## Day 3 (09/20)
- 09:00 Battery Park Ferry (Statue of Liberty and Ellis Island)
- 12:30 Wall Street (New York Stock Exchange and Charging Bull)
- 14:30 9/11 Memorial and Oculus Transportation Hub
- 17:30 Chelsea Market (Lobster roll dinner and artisan market)

## Day 4 (09/21)
- 09:30 The High Line (Elevated linear park walk)
- 11:30 Hudson Yards (The Vessel and Edge observation deck)
- 14:30 SoHo Cast Iron District (Design boutiques and cafe break)
- 17:30 Brooklyn Bridge (Golden hour walk towards DUMBO)
- 19:30 DUMBO Manhattan Bridge photo spot and Grimaldi's Pizza

## Day 5 (09/22)
- 09:30 Museum of Modern Art (MoMA Starry Night and modern art)
- 12:30 Grand Central Terminal (Historic celestial ceiling)
- 14:30 Bryant Park and New York Public Library
- 17:00 Transfer to JFK Airport for Departure`
    }
]

export function AiImportTripWizard({ userId, onComplete }: AiImportTripWizardProps) {
    const { t, lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()
    const templatePills = zh ? TEMPLATE_PILLS_ZH : TEMPLATE_PILLS_EN

    const [importText, setImportText] = useState("")
    const [imagePreview, setImagePreview] = useState<string | null>(null)
    const [isDragging, setIsDragging] = useState(false)
    const [isLoading, setIsLoading] = useState(false)
    const [progressText, setProgressText] = useState<string | null>(null)

    const fileInputRef = useRef<HTMLInputElement>(null)
    const containerRef = useRef<HTMLDivElement>(null)

    // 📋 支援剪貼簿 Paste (文字 / 圖片)
    useEffect(() => {
        const handlePaste = (e: ClipboardEvent) => {
            const items = e.clipboardData?.items
            if (!items) return

            for (let i = 0; i < items.length; i++) {
                const item = items[i]
                if (item.type.startsWith("image/")) {
                    const file = item.getAsFile()
                    if (file) {
                        handleFileSelected(file)
                        haptic.success()
                        toast.success(zh ? "已從剪貼簿貼上行程圖片！" : "Pasted itinerary image from clipboard!")
                        break
                    }
                }
            }
        }

        window.addEventListener("paste", handlePaste)
        return () => window.removeEventListener("paste", handlePaste)
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [zh])

    const handleFileSelected = (file: File) => {
        if (!file.type.startsWith("image/")) {
            toast.error(zh ? "請上傳圖片檔案 (PNG, JPG, WEBP)" : "Please upload an image file (PNG, JPG, WEBP)")
            return
        }
        if (file.size > 10 * 1024 * 1024) {
            toast.error(zh ? "圖片檔案請小於 10MB" : "Image size must be under 10MB")
            return
        }

        const reader = new FileReader()
        reader.onload = (e) => {
            const b64 = e.target?.result as string
            setImagePreview(b64)
            haptic.selection()
        }
        reader.readAsDataURL(file)
    }

    const handleDrop = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(false)
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleFileSelected(e.dataTransfer.files[0])
        }
    }

    const handleDragOver = (e: React.DragEvent) => {
        e.preventDefault()
        setIsDragging(true)
    }

    const handleDragLeave = () => {
        setIsDragging(false)
    }

    const handleApplyTemplate = (content: string) => {
        haptic.selection()
        setImportText(content)
        toast.info(zh ? "已填入範本，點擊下方按鈕開始解析！" : "Template loaded! Click below to start parsing.")
    }

    const handleStartParse = async () => {
        if (!importText.trim() && !imagePreview) {
            haptic.error()
            toast.error(zh ? "請貼上文字行程或上傳行程圖片" : "Please paste itinerary text or upload an image")
            return
        }

        haptic.tap()
        setIsLoading(true)
        setProgressText(imagePreview ? (zh ? "AI 旅伴正在辨識圖片與文字內容..." : "AI Companion is analyzing image and text...") : t('ai_importing_step'))
        const activeUserId = localStorage.getItem("user_uuid") || userId

        try {
            const data = await aiApi.parseMarkdown({
                markdown_text: importText.trim(),
                user_id: activeUserId,
                image_base64: imagePreview || undefined
            })

            setProgressText(t('ai_geocoding_step'))

            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const parsedData = (data as any).data || data
            if (!parsedData.items || parsedData.items.length === 0) {
                toast.error(zh ? "未能從內容中辨識出有效景點，請確認內容格式或清晰度" : "Failed to identify valid spots from content")
                return
            }

            haptic.success()
            toast.success(t('tv_ai_parsed', { count: String(parsedData.items?.length || 0) }))
            onComplete(parsedData)
        } catch (error) {
            haptic.error()
            const msg = error instanceof Error ? error.message : "解析失敗"
            toast.error(zh ? `解析失敗: ${msg}` : `Parsing failed: ${msg}`)
        } finally {
            setIsLoading(false)
            setProgressText(null)
        }
    }

    return (
        <div ref={containerRef} className="space-y-3.5 py-1 select-none">
            {/* 💡 經典範本快選膠囊 */}
            <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs font-semibold text-slate-500 dark:text-slate-400">
                    <span className="flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-bold">
                        <Sparkles className="w-3.5 h-3.5" />
                        <span>{zh ? "範本快選體驗" : "Quick Template Experience"}</span>
                    </span>
                    <span className="text-[11px] text-slate-400">{zh ? "點擊一鍵帶入" : "Click to apply"}</span>
                </div>
                <div className="flex flex-wrap gap-1.5">
                    {templatePills.map((tmpl, i) => (
                        <button
                            key={i}
                            type="button"
                            onClick={() => handleApplyTemplate(tmpl.content)}
                            className="px-2.5 py-1 text-xs rounded-full border border-stone-200/80 dark:border-slate-700 bg-stone-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-emerald-50 dark:hover:bg-slate-700 transition-all cursor-pointer active:scale-95"
                        >
                            {tmpl.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* 🖼️ 圖片/截圖拖曳上傳與貼上區域 */}
            <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-700 dark:text-slate-200 flex items-center justify-between">
                    <span className="flex items-center gap-1.5">
                        <ImageIcon className="w-3.5 h-3.5 text-emerald-500" />
                        行程截圖 / 旅行社DM / LINE 對話 (選填)
                    </span>
                    <span className="text-[11px] text-emerald-600 dark:text-emerald-400 font-normal">
                        支援 Ctrl+V 貼上截圖
                    </span>
                </Label>

                {imagePreview ? (
                    <div className="relative rounded-2xl border border-emerald-300 dark:border-emerald-700/60 bg-emerald-50/40 dark:bg-emerald-950/20 p-2.5 flex items-center gap-3">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img 
                            src={imagePreview} 
                            alt="Preview" 
                            className="w-16 h-16 object-cover rounded-xl border border-emerald-200 dark:border-emerald-800 shrink-0" 
                        />
                        <div className="flex-1 min-w-0">
                            <div className="text-xs font-bold text-emerald-800 dark:text-emerald-200 flex items-center gap-1">
                                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-500" />
                                截圖已就緒
                            </div>
                            <div className="text-[11px] text-slate-500 dark:text-slate-400 truncate">
                                將使用多模態視覺模型深度識別景點
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={() => {
                                haptic.tap()
                                setImagePreview(null)
                            }}
                            className="w-7 h-7 rounded-full bg-stone-200 dark:bg-slate-700 flex items-center justify-center text-slate-600 dark:text-slate-300 hover:bg-red-100 hover:text-red-600 cursor-pointer transition-colors"
                        >
                            <X className="w-3.5 h-3.5" />
                        </button>
                    </div>
                ) : (
                    <div
                        onDrop={handleDrop}
                        onDragOver={handleDragOver}
                        onDragLeave={handleDragLeave}
                        onClick={() => fileInputRef.current?.click()}
                        className={cn(
                            "p-3 rounded-2xl border-2 border-dashed transition-all cursor-pointer flex items-center justify-center gap-3 text-center",
                            isDragging
                                ? "border-emerald-500 bg-emerald-50/60 dark:bg-emerald-950/40 scale-[0.99]"
                                : "border-stone-200 dark:border-slate-700 bg-stone-100/60 dark:bg-slate-800/60 hover:bg-stone-200/50"
                        )}
                    >
                        <input
                            ref={fileInputRef}
                            type="file"
                            accept="image/*"
                            onChange={e => e.target.files?.[0] && handleFileSelected(e.target.files[0])}
                            className="hidden"
                        />
                        <div className="w-8 h-8 rounded-xl bg-emerald-500/10 dark:bg-emerald-400/20 text-emerald-600 dark:text-emerald-400 flex items-center justify-center shrink-0">
                            <UploadCloud className="w-4 h-4" />
                        </div>
                        <div className="text-left">
                            <div className="text-xs font-bold text-slate-700 dark:text-slate-200">
                                點擊或拖曳行程截圖至此
                            </div>
                            <div className="text-[10px] text-slate-400">
                                支援小紅書、旅行社DM、LINE 行程圖片
                            </div>
                        </div>
                    </div>
                )}
            </div>

            {/* 📝 文字與 Markdown 輸入區 */}
            <div className="space-y-1.5">
                <Label className="text-xs font-bold text-slate-700 dark:text-slate-200 flex items-center gap-1.5">
                    <FileText className="w-3.5 h-3.5 text-emerald-500" />
                    {t('ai_import_label')}
                </Label>
                <Textarea
                    value={importText}
                    onChange={e => setImportText(e.target.value)}
                    placeholder={t('ai_import_placeholder')}
                    rows={4}
                    className="resize-none font-mono text-xs rounded-xl bg-stone-100 dark:bg-slate-800"
                />
            </div>

            {/* 🔄 解析中進度狀態 */}
            <AnimatePresence>
                {isLoading && (
                    <motion.div
                        initial={{ opacity: 0, height: 0 }}
                        animate={{ opacity: 1, height: "auto" }}
                        exit={{ opacity: 0, height: 0 }}
                        className="p-4 rounded-2xl bg-emerald-50/90 dark:bg-emerald-950/50 border border-emerald-200 dark:border-emerald-800 flex flex-col items-center justify-center text-center gap-2"
                    >
                        <div className="w-10 h-10 rounded-2xl bg-emerald-500/10 dark:bg-emerald-400/20 flex items-center justify-center">
                            <Loader2 className="w-5 h-5 text-emerald-600 dark:text-emerald-400 animate-spin" />
                        </div>
                        <div className="text-xs font-bold text-emerald-900 dark:text-emerald-200">
                            {progressText || t('ai_importing_step')}
                        </div>
                    </motion.div>
                )}
            </AnimatePresence>

            {/* 🚀 啟動解析按鈕 */}
            {!isLoading && (
                <Button
                    type="button"
                    onClick={handleStartParse}
                    disabled={!importText.trim() && !imagePreview}
                    className="w-full h-11 bg-emerald-600 hover:bg-emerald-700 text-white font-bold rounded-xl shadow-md cursor-pointer transition-all active:scale-[0.99] flex items-center justify-center gap-2"
                >
                    <Sparkles className="w-4 h-4" />
                    <span>{t('ai_import_btn')}</span>
                </Button>
            )}
        </div>
    )
}
