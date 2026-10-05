"use client"

import { useState, useMemo, useSyncExternalStore } from "react"
import { motion, AnimatePresence } from "framer-motion"
import {
    Sun,
    CloudSun,
    CloudRain,
    Cloud,
    CloudSnow,
    CloudLightning,
    MapPin,
    Edit3,
    Clock,
    ChevronDown,
    Droplets,
    Thermometer,
    Wind,
    Eye,
    Sparkles,
    ShieldAlert,
    Mountain,
    Leaf
} from "lucide-react"
import { cn } from "@/lib/utils"
import { DayWeather, LocationInfo } from "@/lib/itinerary-types"
import { getNowInZone } from "@/lib/timezone"
import { useLanguage } from "@/lib/LanguageContext"
import { useHaptic } from "@/lib/hooks"

interface WeatherPanelProps {
    day: number
    weatherData: DayWeather[]
    weatherMode: string
    weatherConfidence: number | null
    elevation: number | null
    resolvedLocation: LocationInfo | null
    currentTimezone: string
    onEditLocation: () => void
}

/**
 * 🎨 OKLCH 色溫分段線性插值算法 (Apple HIG 色溫光譜)
 * 涵蓋 -20°C (極寒深藍) 至 40°C (酷暑鮮紅)
 */
function lerp(a: number, b: number, t: number): number {
    return a + (b - a) * t
}

const TEMP_COLOR_STOPS: [number, number, number, number][] = [
    [-20, 0.65, 0.10, 250], // 深藍
    [-10, 0.62, 0.12, 240], // 冰藍
    [0,   0.68, 0.11, 200], // 青藍 (冰點)
    [10,  0.72, 0.17, 145], // 翠綠
    [20,  0.84, 0.18,  95], // 暖黃
    [30,  0.72, 0.18,  55], // 橙色
    [40,  0.62, 0.22,  25], // 鮮紅
]

function tempToColor(tempC: number): string {
    const stops = TEMP_COLOR_STOPS
    if (tempC <= stops[0][0]) {
        const [, l, c, h] = stops[0]
        return `oklch(${l} ${c} ${h})`
    }
    if (tempC >= stops[stops.length - 1][0]) {
        const [, l, c, h] = stops[stops.length - 1]
        return `oklch(${l} ${c} ${h})`
    }

    for (let i = 0; i < stops.length - 1; i++) {
        const [t0, l0, c0, h0] = stops[i]
        const [t1, l1, c1, h1] = stops[i + 1]
        if (tempC >= t0 && tempC <= t1) {
            const ratio = (tempC - t0) / (t1 - t0)
            const l = lerp(l0, l1, ratio)
            const c = lerp(c0, c1, ratio)
            const h = lerp(h0, h1, ratio)
            return `oklch(${l.toFixed(3)} ${c.toFixed(3)} ${h.toFixed(1)})`
        }
    }
    return `oklch(0.75 0.15 100)`
}

/**
 * ⛅ WMO 天氣代碼圖標映射
 */
function getWeatherIcon(code: number, className = "w-5 h-5") {
    if (code === 0) return <Sun className={cn(className, "text-amber-400")} />
    if (code >= 1 && code <= 3) return <CloudSun className={cn(className, "text-amber-400/90")} />
    if (code === 45 || code === 48) return <Cloud className={cn(className, "text-slate-400")} />
    if ((code >= 51 && code <= 67) || (code >= 80 && code <= 82)) return <CloudRain className={cn(className, "text-blue-400")} />
    if ((code >= 71 && code <= 77) || (code >= 85 && code <= 86)) return <CloudSnow className={cn(className, "text-sky-300")} />
    if (code >= 95 && code <= 99) return <CloudLightning className={cn(className, "text-indigo-400")} />
    return <Sun className={cn(className, "text-amber-400")} />
}

const emptySubscribe = () => () => {}

export function WeatherPanel({
    day,
    weatherData = [],
    weatherMode,
    weatherConfidence,
    elevation,
    resolvedLocation,
    currentTimezone,
    onEditLocation
}: WeatherPanelProps) {
    const { t, lang } = useLanguage()
    const zh = lang === "zh"
    const haptic = useHaptic()

    // 📱 雙態摺疊狀態 (預設精緻收合，點擊展開 Bento 矩陣)
    const [isExpanded, setIsExpanded] = useState(false)
    const isMounted = useSyncExternalStore(emptySubscribe, () => true, () => false)

    // 🛡️ 1. 空資料與數值邊界防護 (Defensive Data Boundary)
    const hasData = Array.isArray(weatherData) && weatherData.length > 0
    const temps = useMemo(() => (hasData ? weatherData.map((w) => w.temp) : [20]), [hasData, weatherData])
    const minTemp = hasData ? Math.min(...temps) : 20
    const maxTemp = hasData ? Math.max(...temps) : 20

    // 🛡️ 2. 溫差分母歸零防禦 (Zero-Delta Guard) - 杜絕陰雨天恆溫除以零造成 NaN
    const tempDelta = Math.max(1, maxTemp - minTemp)

    const currentItem = hasData ? weatherData[0] : null
    const currentTemp = currentItem ? currentItem.temp : 20
    const currentWeatherCode = currentItem ? currentItem.code : 0

    // 🛡️ 3. WBGT (中暑熱壓力指數) 確定性簡化計算
    const calculateWBGT = (temp: number, rh: number) => {
        const safeTemp = isNaN(temp) ? 20 : temp
        const safeRH = isNaN(rh) ? 50 : rh
        return 0.735 * safeTemp + 0.0374 * safeRH + 0.00292 * safeTemp * safeRH - 4.06
    }

    const localTimeStr = isMounted ? getNowInZone(currentTimezone) : "--:--"

    // 🌅 4. 動態天候時段環境光影微漸層 (Ambient Mesh Gradient)
    const ambientMeshStyle = useMemo(() => {
        if (!isMounted) return "from-slate-100/80 to-slate-200/40 dark:from-slate-900/60 dark:to-slate-950/80"

        const hour = parseInt(localTimeStr.split(":")[0], 10)
        const isRain = currentWeatherCode >= 51 && currentWeatherCode <= 82

        if (isRain) {
            return "from-slate-300/35 via-blue-200/25 to-slate-400/20 dark:from-slate-900/80 dark:via-blue-950/60 dark:to-slate-950/90"
        }
        if (hour >= 5 && hour < 8) {
            // 清晨金曦
            return "from-amber-200/35 via-rose-100/25 to-sky-200/20 dark:from-amber-950/40 dark:via-rose-950/30 dark:to-slate-950/80"
        }
        if (hour >= 8 && hour < 17) {
            // 正午蔚藍
            return "from-sky-200/40 via-blue-100/25 to-indigo-100/20 dark:from-sky-950/50 dark:via-blue-950/40 dark:to-slate-950/80"
        }
        if (hour >= 17 && hour < 19) {
            // 日落晚霞
            return "from-orange-200/35 via-purple-100/25 to-rose-200/20 dark:from-orange-950/40 dark:via-purple-950/30 dark:to-slate-950/80"
        }
        // 深夜靛青
        return "from-indigo-100/30 via-slate-100/20 to-purple-100/20 dark:from-indigo-950/60 dark:via-slate-950/80 dark:to-black/80"
    }, [isMounted, localTimeStr, currentWeatherCode])

    // 🤖 5. AI 動態穿衣與天候叮嚀提取 (完整保留 Audit 5.0 特殊地點與邊界邏輯)
    const aiAdvice = useMemo(() => {
        if (!hasData) return null

        const maxPrecip = Math.max(...weatherData.map((w) => w.precipitation_probability ?? 0))
        const maxUV = Math.max(...weatherData.map((w) => w.uvIndex ?? 0))
        const avgRH = weatherData[Math.floor(weatherData.length / 2)]?.humidity ?? 50
        const avgTemp = (maxTemp + minTemp) / 2
        const isHighElev = elevation && elevation > 1000
        const isVolatile = weatherConfidence !== null && weatherConfidence < 50
        const wbgt = calculateWBGT(avgTemp, avgRH)
        const isHeatStroke = wbgt > 28

        // 穿衣指南推算 (6 階完整對應)
        let clothText = t("w_cloth_tshirt")
        if (avgTemp > 28) clothText = t("w_cloth_tank")
        else if (avgTemp > 22) clothText = t("w_cloth_tshirt")
        else if (avgTemp > 15) clothText = t("w_cloth_longsleeve")
        else if (avgTemp > 10) clothText = t("w_cloth_jacket")
        else if (avgTemp > 5) clothText = t("w_cloth_coat")
        else clothText = t("w_cloth_parka")

        // 完整 AI 氣象建議字串 (保留溫差、極端天氣、海拔與特殊地點邏輯)
        let adviceText = t("w_advice_range", { min: String(Math.round(minTemp)), max: String(Math.round(maxTemp)) })
        let isAlert = false

        if (isHeatStroke) {
            adviceText = t("w_advice_heatstroke", { wbgt: wbgt.toFixed(1) })
            isAlert = true
        } else if (isVolatile) {
            adviceText = t("w_advice_unstable", { pct: String(weatherConfidence) })
            isAlert = true
        } else if (maxPrecip > 60) {
            adviceText += " " + t("w_advice_rain")
            isAlert = true
        } else if (maxUV > 7) {
            adviceText += " " + t("w_advice_uv")
        } else if (avgTemp > 28) {
            adviceText += " " + t("w_advice_humid")
        } else if (avgTemp < 10) {
            adviceText += " " + t("w_advice_cold")
        } else {
            adviceText += " " + t("w_advice_clear")
        }

        if (isHighElev) {
            adviceText += " " + t("w_advice_elevation", { elev: String(Math.round(elevation!)) })
        }

        // 🔍 特殊地點邏輯 (市場 / 晴空塔觀景台)
        const locLower = resolvedLocation?.name.toLowerCase() || ""
        if (locLower.includes("market") || locLower.includes("市場")) {
            adviceText += " " + t("w_advice_market")
        }
        if (locLower.includes("tower") || locLower.includes("skytree") || locLower.includes("塔") || locLower.includes("展望台")) {
            adviceText += " " + t("w_advice_tower")
        }

        return {
            clothText,
            adviceText,
            isAlert,
        }
    }, [hasData, weatherData, maxTemp, minTemp, elevation, weatherConfidence, resolvedLocation?.name, t])

    // 觸覺切換折疊狀態
    const toggleExpand = () => {
        haptic.selection()
        setIsExpanded((prev) => !prev)
    }

    return (
        <div className="w-full px-4 pt-2 pb-1" data-day={day}>
            {/* ──────────────────────────────────────────────────────────── */}
            {/* 📱 iOS 天候一體化容器 (Single Backdrop Blur Evades GPU Lag)      */}
            {/* ──────────────────────────────────────────────────────────── */}
            <div
                className={cn(
                    "w-full rounded-3xl p-4 transition-all duration-300",
                    "bg-linear-to-br border border-white/60 dark:border-white/10 shadow-sm",
                    "backdrop-blur-xl",
                    ambientMeshStyle
                )}
            >
                {/* 1. 頂部地點、時鐘與模式標籤列 */}
                <div className="flex items-center justify-between gap-2 mb-3">
                    <button
                        type="button"
                        onClick={onEditLocation}
                        className="flex items-center gap-1.5 px-2 py-1 -ml-1 rounded-xl hover:bg-black/5 dark:hover:bg-white/10 transition-colors group select-none min-w-0"
                    >
                        <MapPin className="w-3.5 h-3.5 text-primary/70 group-hover:text-primary transition-colors shrink-0" />
                        <span className="text-xs font-bold text-foreground truncate max-w-37.5 sm:max-w-xs">
                            {resolvedLocation?.name || (
                                <span className="inline-block w-16 h-3 bg-foreground/10 animate-pulse rounded" />
                            )}
                        </span>
                        {/* 🌐 GPS 經緯度座標微標籤 */}
                        {resolvedLocation && (
                            <span className="text-[9px] font-mono font-normal text-muted-foreground border border-border/40 px-1 rounded hidden sm:inline-block shrink-0">
                                {resolvedLocation.lat.toFixed(2)}, {resolvedLocation.lng.toFixed(2)}
                            </span>
                        )}
                        <Edit3 className="w-2.5 h-2.5 text-muted-foreground opacity-60 group-hover:opacity-100 transition-opacity shrink-0" />
                    </button>

                    <div className="flex items-center gap-1.5 flex-wrap justify-end">
                        {/* 氣象模式徽章 */}
                        <span
                            className={cn(
                                "text-[10px] font-semibold px-2 py-0.5 rounded-full border flex items-center gap-1 select-none",
                                weatherMode === "live"
                                    ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                                    : weatherMode === "forecast"
                                    ? "bg-blue-500/10 border-blue-500/30 text-blue-600 dark:text-blue-400"
                                    : weatherMode === "seasonal"
                                    ? "bg-purple-500/10 border-purple-500/30 text-purple-600 dark:text-purple-400"
                                    : "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                            )}
                        >
                            <span
                                className={cn(
                                    "w-1 h-1 rounded-full",
                                    weatherMode === "live"
                                        ? "bg-emerald-500 animate-pulse"
                                        : weatherMode === "forecast"
                                        ? "bg-blue-500"
                                        : weatherMode === "seasonal"
                                        ? "bg-purple-500"
                                        : "bg-amber-500"
                                )}
                            />
                            {weatherMode === "live" && (t("w_mode_live") || (zh ? "即時氣象" : "Live"))}
                            {weatherMode === "forecast" && (t("w_mode_forecast") || (zh ? "預報" : "Forecast"))}
                            {weatherMode === "seasonal" && (t("w_mode_seasonal") || (zh ? "季節推估" : "Seasonal"))}
                            {weatherMode === "trend" && (t("w_mode_trend") || (zh ? "歷史氣候" : "Trend"))}
                            {(weatherMode === "seasonal" || weatherMode === "trend") && (
                                <span className="text-[8px] opacity-60">({t("w_reference_only") || (zh ? "僅供參考" : "Reference")})</span>
                            )}
                        </span>

                        {/* 🛰️ ECMWF 精準預報徽章 */}
                        {weatherMode === "forecast" && (
                            <span className="hidden sm:inline-flex items-center px-1.5 py-0.5 rounded text-[9px] font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
                                {t("w_ecmwf_badge")}
                            </span>
                        )}

                        {/* 🎯 預報信心度徽章 */}
                        {weatherConfidence !== null && (
                            <span
                                className={cn(
                                    "px-1.5 py-0.5 rounded-full text-[9px] font-bold border transition-all duration-300 select-none",
                                    weatherConfidence >= 80
                                        ? "bg-emerald-500/10 border-emerald-500/30 text-emerald-600 dark:text-emerald-400"
                                        : weatherConfidence >= 50
                                        ? "bg-amber-500/10 border-amber-500/30 text-amber-600 dark:text-amber-400"
                                        : "bg-rose-500/10 border-rose-500/30 text-rose-600 dark:text-rose-400"
                                )}
                            >
                                {t("w_confidence", { value: String(weatherConfidence) })}
                            </span>
                        )}

                        {/* 當地時間 */}
                        <div className="flex items-center gap-1 text-[10px] font-mono text-muted-foreground bg-background/50 dark:bg-zinc-800/50 px-2 py-0.5 rounded-md border border-border/40">
                            <Clock className="w-2.5 h-2.5 text-amber-500 shrink-0" />
                            <span>{localTimeStr}</span>
                        </div>
                    </div>
                </div>

                {/* 2. Apple Weather Hero 核心氣溫區域 */}
                <div className="flex items-baseline justify-between gap-4 mb-2.5">
                    <div className="flex items-baseline gap-2.5">
                        <div className="shrink-0">{getWeatherIcon(currentWeatherCode, "w-8 h-8")}</div>
                        <div className="text-4xl sm:text-5xl font-extrabold text-foreground tracking-tighter tabular-nums leading-none">
                            {hasData ? `${Math.round(currentTemp)}°` : "--°"}
                        </div>
                        <div className="text-xs font-semibold text-muted-foreground">
                            {hasData ? (
                                currentWeatherCode <= 3
                                    ? zh ? "晴朗天候" : "Clear Sky"
                                    : currentWeatherCode >= 51 && currentWeatherCode <= 82
                                    ? zh ? "短暫陣雨" : "Showers"
                                    : zh ? "多雲遮日" : "Cloudy"
                            ) : (
                                zh ? "數據獲取中" : "Loading..."
                            )}
                        </div>
                    </div>

                    {/* 今日高低溫跨度 */}
                    <div className="text-right shrink-0">
                        <div className="text-xs font-mono font-medium text-foreground tabular-nums">
                            {hasData ? (
                                <>
                                    <span className="text-rose-500 font-bold">H:{Math.round(maxTemp)}°</span>{" "}
                                    <span className="text-sky-500 font-bold">L:{Math.round(minTemp)}°</span>
                                </>
                            ) : (
                                "--° / --°"
                            )}
                        </div>
                    </div>
                </div>

                {/* 3. AI 智能行前氣象叮嚀膠囊 (iOS Dynamic Glass Pill) */}
                {aiAdvice && (
                    <div
                        className={cn(
                            "w-full mb-3 px-3 py-2 rounded-2xl border flex items-start gap-2.5 transition-colors select-none",
                            aiAdvice.isAlert
                                ? "bg-amber-500/10 border-amber-500/30 text-amber-900 dark:text-amber-200"
                                : "bg-white/60 dark:bg-zinc-800/60 border-white/40 dark:border-white/10 text-foreground"
                        )}
                    >
                        <Sparkles
                            className={cn(
                                "w-4 h-4 mt-0.5 shrink-0",
                                aiAdvice.isAlert ? "text-amber-500 animate-pulse" : "text-primary"
                            )}
                        />
                        <div className="text-[11px] leading-relaxed flex-1">
                            <span className="font-semibold text-primary dark:text-primary-foreground mr-1.5">
                                {zh ? "穿衣指南：" : "Attire: "}{aiAdvice.clothText}
                            </span>
                            <span className="opacity-90">{aiAdvice.adviceText}</span>
                        </div>
                    </div>
                )}

                {/* 4. 24 小時橫向時間軸滾動帶 (Hourly Scrubber Strip) */}
                <div className="relative w-full mb-2">
                    <div
                        className="flex gap-2 overflow-x-auto no-scrollbar pb-1.5 pt-0.5 touch-pan-x overscroll-x-contain"
                        style={{ WebkitOverflowScrolling: "touch" }}
                    >
                        {hasData ? (
                            weatherData.map((hourItem, idx) => {
                                const rainProb = hourItem.precipitation_probability ?? 0
                                const tempColor = tempToColor(hourItem.temp)
                                const isNow = idx === 0

                                return (
                                    <div
                                        key={hourItem.time || idx}
                                        className={cn(
                                            "flex flex-col items-center min-w-14 py-2 px-1.5 rounded-2xl border shrink-0 transition-transform active:scale-95",
                                            "bg-white/60 dark:bg-zinc-800/60 border-white/50 dark:border-white/10 shadow-xs"
                                        )}
                                    >
                                        {/* 時間標籤 */}
                                        <span className="text-[10px] font-mono text-muted-foreground leading-none mb-1.5">
                                            {isNow ? (zh ? "現在" : "Now") : hourItem.time}
                                        </span>

                                        {/* 天氣圖標 */}
                                        <div className="my-0.5">{getWeatherIcon(hourItem.code, "w-4 h-4")}</div>

                                        {/* 條件式水滴降雨率標籤 (僅在 >= 20% 時優雅浮現) */}
                                        <div className="h-3.5 flex items-center justify-center my-0.5">
                                            {rainProb >= 20 ? (
                                                <span className="inline-flex items-center text-[9px] font-bold text-sky-500 font-mono leading-none">
                                                    <Droplets className="w-2 h-2 mr-0.5" />
                                                    {rainProb}%
                                                </span>
                                            ) : (
                                                <span className="w-1 h-1 rounded-full bg-border/40" />
                                            )}
                                        </div>

                                        {/* 氣溫數值與動態 OKLCH 彩點 */}
                                        <div className="flex items-center gap-0.5 mt-0.5">
                                            <span
                                                className="w-1.5 h-1.5 rounded-full shrink-0"
                                                style={{ backgroundColor: tempColor }}
                                            />
                                            <span className="text-xs font-bold text-foreground font-mono tabular-nums leading-none">
                                                {Math.round(hourItem.temp)}°
                                            </span>
                                        </div>

                                        {/* 迷你溫度跨度條 (Apple Weather signature range indicator) */}
                                        <div className="w-7 h-1 bg-black/5 dark:bg-white/10 rounded-full overflow-hidden mt-1">
                                            <div
                                                className="h-full rounded-full transition-all duration-300"
                                                style={{
                                                    width: `${Math.max(15, Math.round(((hourItem.temp - minTemp) / tempDelta) * 100))}%`,
                                                    backgroundColor: tempColor
                                                }}
                                            />
                                        </div>
                                    </div>
                                )
                            })
                        ) : (
                            // 骨架屏防護
                            Array.from({ length: 12 }).map((_, i) => (
                                <div
                                    key={i}
                                    className="flex flex-col items-center min-w-14 py-2 px-1.5 rounded-2xl border border-white/20 bg-white/30 dark:bg-zinc-800/30 animate-pulse shrink-0"
                                >
                                    <div className="w-6 h-2 bg-foreground/10 rounded mb-2" />
                                    <div className="w-4 h-4 bg-foreground/10 rounded-full my-1" />
                                    <div className="w-8 h-2 bg-foreground/10 rounded mt-2" />
                                </div>
                            ))
                        )}
                    </div>
                </div>

                {/* 5. 展開 / 收合 Bento 矩陣手柄列 */}
                <button
                    type="button"
                    onClick={toggleExpand}
                    className="w-full pt-1 pb-0.5 flex items-center justify-center gap-1.5 text-xs font-semibold text-muted-foreground hover:text-foreground transition-colors group select-none"
                >
                    <span>
                        {zh
                            ? isExpanded
                                ? "收合詳細氣象"
                                : "查看詳細氣象"
                            : isExpanded
                            ? "Collapse Details"
                            : "More Weather Details"}
                    </span>
                    <ChevronDown
                        className={cn(
                            "w-3.5 h-3.5 transition-transform duration-300 text-muted-foreground group-hover:text-primary",
                            isExpanded && "rotate-180"
                        )}
                    />
                </button>

                {/* 6. 展開態：2x2 Bento 矩陣 (Smooth Spring Animation) */}
                <AnimatePresence initial={false}>
                    {isExpanded && (
                        <motion.div
                            initial={{ opacity: 0, height: 0 }}
                            animate={{ opacity: 1, height: "auto" }}
                            exit={{ opacity: 0, height: 0 }}
                            transition={{ duration: 0.35, ease: [0.16, 1, 0.3, 1] }}
                            className="overflow-hidden pt-3 border-t border-white/40 dark:border-white/10 mt-2"
                        >
                            <div className="grid grid-cols-2 gap-2.5">
                                {/* Bento 卡片 1: 體感與中暑防護 */}
                                <div className="p-3 rounded-2xl bg-white/70 dark:bg-zinc-800/70 border border-white/60 dark:border-white/10 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center gap-1 text-[10px] font-semibold uppercase text-muted-foreground">
                                        <Thermometer className="w-3.5 h-3.5 text-amber-500" />
                                        <span>{t("w_apparent") || (zh ? "體感溫度" : "Feels Like")}</span>
                                    </div>
                                    <div className="my-1.5">
                                        <div className="text-xl font-bold text-foreground tabular-nums font-mono leading-none">
                                            {hasData && currentItem?.apparent_temperature !== undefined
                                                ? `${Math.round(currentItem.apparent_temperature)}°C`
                                                : `${Math.round(currentTemp)}°C`}
                                        </div>
                                        <div className="text-[10px] text-muted-foreground mt-0.5">
                                            {(() => {
                                                const appTemp = currentItem?.apparent_temperature ?? currentTemp
                                                let feeling = t("w_comfort_pleasant") || (zh ? "體感舒適" : "Pleasant")
                                                if (appTemp >= 35) feeling = t("w_comfort_extreme") || (zh ? "極度悶熱" : "Extreme heat")
                                                else if (appTemp >= 28) feeling = t("w_comfort_hot") || (zh ? "偏熱" : "Hot")
                                                else if (appTemp >= 20) feeling = t("w_comfort_pleasant") || (zh ? "體感舒適" : "Pleasant")
                                                else if (appTemp >= 10) feeling = t("w_comfort_cool") || (zh ? "微涼" : "Cool")
                                                else feeling = t("w_comfort_cold") || (zh ? "寒冷" : "Cold")
                                                return feeling
                                            })()}
                                        </div>
                                    </div>
                                    {/* WBGT 中暑警告標籤 */}
                                    {(() => {
                                        const avgRH = currentItem?.humidity ?? 50
                                        const wbgt = calculateWBGT(currentTemp, avgRH)
                                        if (wbgt > 28) {
                                            return (
                                                <div className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-md bg-rose-500/10 text-rose-600 dark:text-rose-400 text-[9px] font-bold">
                                                    <ShieldAlert className="w-2.5 h-2.5 animate-pulse" />
                                                    WBGT {wbgt.toFixed(1)} {zh ? "防中暑 🔥" : "Alert 🔥"}
                                                </div>
                                            )
                                        }
                                        return (
                                            <div className="text-[9px] text-muted-foreground/80">
                                                {zh ? "溫濕平衡適中" : "Balanced humidity"}
                                            </div>
                                        )
                                    })()}
                                </div>

                                {/* Bento 卡片 2: 降雨機率與濕度 */}
                                <div className="p-3 rounded-2xl bg-white/70 dark:bg-zinc-800/70 border border-white/60 dark:border-white/10 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center gap-1 text-[10px] font-semibold uppercase text-muted-foreground">
                                        <Droplets className="w-3.5 h-3.5 text-sky-500" />
                                        <span>{weatherData[0]?.isSeasonalEstimate ? (t("w_rain_trend") || (zh ? "降雨趨勢" : "Precip Trend")) : (t("w_rain_prob") || (zh ? "降雨與濕度" : "Precip & RH"))}</span>
                                    </div>
                                    <div className="my-1.5">
                                        <div className="text-xl font-bold text-foreground tabular-nums font-mono leading-none">
                                            {hasData ? (
                                                weatherData[0]?.isSeasonalEstimate ? (
                                                    (() => {
                                                        const trend = weatherData[0]?.precipTrend
                                                        if (trend === "wet") return <span className="text-blue-600 dark:text-blue-400">{t("w_trend_wet")}</span>
                                                        if (trend === "unstable") return <span className="text-amber-600 dark:text-amber-400">{t("w_trend_unstable")}</span>
                                                        return <span className="text-emerald-600 dark:text-emerald-400">{t("w_trend_dry")}</span>
                                                    })()
                                                ) : (
                                                    `${Math.max(...weatherData.map((w) => w.precipitation_probability ?? 0))}%`
                                                )
                                            ) : "0%"}
                                        </div>
                                        <div className="text-[10px] text-muted-foreground mt-0.5">
                                            {t("w_humidity") || (zh ? "相對濕度" : "Humidity")}: {currentItem?.humidity ?? 50}%
                                        </div>
                                        {weatherData[0]?.isSeasonalEstimate && (
                                            <div className="text-[8px] text-muted-foreground/70 mt-0.5">{t("w_trend_disclaimer")}</div>
                                        )}
                                    </div>
                                    {/* 水滴微進度條 */}
                                    <div className="w-full h-1.5 bg-sky-100 dark:bg-zinc-700 rounded-full overflow-hidden">
                                        <div
                                            className="h-full bg-sky-500 rounded-full transition-all duration-300"
                                            style={{
                                                width: `${Math.min(100, Math.max(0, currentItem?.humidity ?? 50))}%`
                                            }}
                                        />
                                    </div>
                                </div>

                                {/* Bento 卡片 3: 紫外線與防曬 */}
                                <div className="p-3 rounded-2xl bg-white/70 dark:bg-zinc-800/70 border border-white/60 dark:border-white/10 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center gap-1 text-[10px] font-semibold uppercase text-muted-foreground">
                                        <Sun className="w-3.5 h-3.5 text-amber-500" />
                                        <span>{t("w_uv") || (zh ? "紫外線指數" : "UV Index")}</span>
                                    </div>
                                    <div className="my-1.5">
                                        {(() => {
                                            const maxUV = hasData ? Math.max(...weatherData.map((w) => w.uvIndex ?? 0)) : 0
                                            const uvLevel = maxUV > 7 ? (t("w_uv_extreme") || (zh ? "極高" : "Very High"))
                                                : maxUV > 5 ? (t("w_uv_high") || (zh ? "高" : "High"))
                                                : maxUV > 2 ? (t("w_uv_moderate") || (zh ? "中等" : "Moderate"))
                                                : (t("w_uv_low") || (zh ? "微弱" : "Low"))
                                            return (
                                                <>
                                                    <div className="text-xl font-bold text-foreground tabular-nums font-mono leading-none">
                                                        {maxUV} <span className="text-xs font-semibold text-muted-foreground">({uvLevel})</span>
                                                    </div>
                                                    <div className="text-[10px] text-muted-foreground mt-0.5">
                                                        {t("w_clothing") || (zh ? "穿衣" : "Clothing")}: {aiAdvice?.clothText || t("w_cloth_tshirt")}
                                                    </div>
                                                </>
                                            )
                                        })()}
                                    </div>
                                    {/* UV 光譜條 (0-11) */}
                                    <div className="w-full h-1.5 bg-linear-to-r from-emerald-400 via-amber-400 to-rose-500 rounded-full opacity-80" />
                                </div>

                                {/* Bento 卡片 4: 風速、空氣品質與海拔 */}
                                <div className="p-3 rounded-2xl bg-white/70 dark:bg-zinc-800/70 border border-white/60 dark:border-white/10 shadow-xs flex flex-col justify-between">
                                    <div className="flex items-center gap-1 text-[10px] font-semibold uppercase text-muted-foreground">
                                        <Wind className="w-3.5 h-3.5 text-indigo-500" />
                                        <span>{zh ? "風速與空氣" : "Wind & AQI"}</span>
                                    </div>
                                    <div className="my-1.5">
                                        {(() => {
                                            const maxWind = hasData ? Math.max(...weatherData.map((w) => w.windSpeed ?? 0)) : 0
                                            return (
                                                <div className="text-xl font-bold text-foreground tabular-nums font-mono leading-none">
                                                    {Math.round(maxWind)} <span className="text-xs font-semibold text-muted-foreground">km/h</span>
                                                </div>
                                            )
                                        })()}
                                        <div className="flex items-center gap-2 text-[10px] text-muted-foreground mt-0.5">
                                            {/* AQI 標籤 */}
                                            {(() => {
                                                const validAQI = weatherData.filter((w) => w.airQuality !== undefined)
                                                if (validAQI.length > 0) {
                                                    const maxAQI = Math.max(...validAQI.map((w) => w.airQuality!))
                                                    let level = t("w_aqi_good") || (zh ? "良好" : "Good")
                                                    let color = "text-emerald-600 dark:text-emerald-400"
                                                    if (maxAQI > 300) { level = t("w_aqi_hazardous") || (zh ? "危險" : "Hazardous"); color = "text-rose-600" }
                                                    else if (maxAQI > 200) { level = t("w_aqi_very_unhealthy") || (zh ? "非常有害" : "Very Unhealthy"); color = "text-rose-500" }
                                                    else if (maxAQI > 150) { level = t("w_aqi_unhealthy") || (zh ? "有害" : "Unhealthy"); color = "text-orange-500" }
                                                    else if (maxAQI > 100) { level = t("w_aqi_sensitive") || (zh ? "敏感有害" : "Sensitive"); color = "text-yellow-600 dark:text-yellow-400" }
                                                    else if (maxAQI > 50) { level = t("w_aqi_moderate") || (zh ? "普通" : "Moderate"); color = "text-yellow-500" }
                                                    return (
                                                        <span className={cn("flex items-center gap-0.5 font-semibold", color)}>
                                                            <Leaf className="w-2.5 h-2.5" />
                                                            AQI {maxAQI} ({level})
                                                        </span>
                                                    )
                                                }
                                                return <span className="text-muted-foreground/60">{t("w_aqi_nodata") || "--"}</span>
                                            })()}
                                            {/* 能見度 */}
                                            {(() => {
                                                const vis = currentItem?.visibility
                                                if (vis !== undefined && vis !== null) {
                                                    const visText = vis >= 10000 ? `${(vis / 1000).toFixed(0)}km (${t("w_vis_good") || (zh ? "良好" : "Good")})`
                                                        : vis >= 5000 ? `${(vis / 1000).toFixed(1)}km (${t("w_vis_fair") || (zh ? "普通" : "Fair")})`
                                                        : `${(vis / 1000).toFixed(1)}km (${t("w_vis_poor") || (zh ? "差" : "Poor")})`
                                                    return (
                                                        <span className="flex items-center gap-0.5">
                                                            <Eye className="w-2.5 h-2.5" />
                                                            {visText}
                                                        </span>
                                                    )
                                                }
                                                return null
                                            })()}
                                        </div>
                                    </div>
                                    {/* 海拔標註 */}
                                    <div className="flex items-center gap-1 text-[9px] text-muted-foreground/80 font-mono">
                                        <Mountain className="w-2.5 h-2.5" />
                                        <span>{t("w_elevation") || (zh ? "海拔" : "Elev")}: {elevation !== null ? `${Math.round(elevation)}m` : "--"}</span>
                                    </div>
                                </div>
                            </div>

                            {/* 7. 數據來源與版權 (Data Attribution) */}
                            <div className="flex items-center justify-between pt-2.5 px-1 text-[9px] text-muted-foreground/60 select-none">
                                <a
                                    href="https://open-meteo.com/"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="hover:text-primary transition-colors underline-offset-2 hover:underline"
                                >
                                    Weather data by Open-Meteo & ECMWF
                                </a>
                                {weatherConfidence !== null && (
                                    <span>{t("w_confidence", { value: String(weatherConfidence) })}</span>
                                )}
                            </div>
                        </motion.div>
                    )}
                </AnimatePresence>
            </div>
        </div>
    )
}
