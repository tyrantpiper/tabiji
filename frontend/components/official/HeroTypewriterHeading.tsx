"use client"

import React, { useState, useEffect } from "react"
import { motion, useReducedMotion } from "framer-motion"
import { cn } from "@/lib/utils"

export interface HeroTypewriterHeadingProps {
  /** 第一行文字 (例: "走過的路，") */
  line1: string
  /** 第二行文字 (例: "都在這裡發光。") */
  line2: string
  /** 容器樣式 */
  className?: string
  /** 每個字元間隔 (ms)，預設 85ms */
  charDelay?: number
  /** 第一行打完至第二行開始間隔 (ms)，預設 350ms */
  lineDelay?: number
  /** 全部打完後光標淡出延遲 (ms)，預設 400ms */
  cursorFadeDelay?: number
}

export function HeroTypewriterHeading(props: HeroTypewriterHeadingProps) {
  return (
    <HeroTypewriterHeadingContent
      key={`${props.line1}::${props.line2}`}
      {...props}
    />
  )
}

function HeroTypewriterHeadingContent({
  line1,
  line2,
  className,
  charDelay = 85,
  lineDelay = 350,
  cursorFadeDelay = 400,
}: HeroTypewriterHeadingProps) {
  const shouldReduceMotion = useReducedMotion()

  const [charIndex1, setCharIndex1] = useState(0)
  const [charIndex2, setCharIndex2] = useState(0)
  const [currentLine, setCurrentLine] = useState<1 | 2 | 3>(1)
  const [cursorVisible, setCursorVisible] = useState(true)

  useEffect(() => {
    if (shouldReduceMotion) {
      return
    }

    let idx1 = 0
    let idx2 = 0
    let activeInterval: NodeJS.Timeout | null = null
    let activeTimer: NodeJS.Timeout | null = null

    // 階段 1: 打第一行
    activeInterval = setInterval(() => {
      idx1 += 1
      setCharIndex1(idx1)

      if (idx1 >= line1.length) {
        if (activeInterval) clearInterval(activeInterval)

        // 階段 2: 停頓後切換至第二行
        activeTimer = setTimeout(() => {
          setCurrentLine(2)

          activeInterval = setInterval(() => {
            idx2 += 1
            setCharIndex2(idx2)

            if (idx2 >= line2.length) {
              if (activeInterval) clearInterval(activeInterval)
              setCurrentLine(3)

              // 階段 3: 完成後游標淡出
              activeTimer = setTimeout(() => {
                setCursorVisible(false)
              }, cursorFadeDelay)
            }
          }, charDelay)
        }, lineDelay)
      }
    }, charDelay)

    return () => {
      if (activeInterval) clearInterval(activeInterval)
      if (activeTimer) clearTimeout(activeTimer)
    }
  }, [line1, line2, charDelay, lineDelay, cursorFadeDelay, shouldReduceMotion])

  const displayLine1 = shouldReduceMotion ? line1 : line1.slice(0, charIndex1)
  const displayLine2 = shouldReduceMotion ? line2 : line2.slice(0, charIndex2)
  const showCursor = !shouldReduceMotion && cursorVisible

  return (
    <h2
      className={cn(
        "text-3xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-stone-900 dark:text-stone-50 leading-[1.18] sm:leading-[1.12] text-balance break-words",
        className
      )}
    >
      {/* 1. a11y & SEO 完整文字 (視覺隱藏) */}
      <span className="sr-only">
        {line1}
        {line2}
      </span>

      {/* 2. 視覺打字逐字浮現層 */}
      <span aria-hidden="true" className="block whitespace-pre-wrap leading-[1.22] pb-1 pr-2">
        {displayLine1}
        {currentLine === 1 && showCursor && (
          <motion.span
            aria-hidden="true"
            initial={{ opacity: 1 }}
            animate={{ opacity: [1, 0, 1] }}
            transition={{ duration: 0.8, repeat: Infinity, ease: "easeInOut" }}
            className="inline-block ml-1 w-[3px] h-[0.85em] bg-emerald-600 dark:bg-emerald-400 rounded-full align-middle select-none"
          />
        )}
      </span>

      <span
        aria-hidden="true"
        className="block bg-gradient-to-r from-[#0B3026] via-emerald-800 to-amber-600 dark:from-emerald-300 dark:via-teal-200 dark:to-amber-300 bg-clip-text text-transparent whitespace-pre-wrap leading-[1.24] pb-2.5 sm:pb-3.5 -mb-2.5 sm:-mb-3.5 pr-2"
      >
        {displayLine2}
        {currentLine >= 2 && showCursor && (
          <motion.span
            aria-hidden="true"
            initial={{ opacity: 1 }}
            animate={
              currentLine === 3
                ? { opacity: 0 }
                : { opacity: [1, 0, 1] }
            }
            transition={
              currentLine === 3
                ? { duration: 0.4, ease: "easeOut" }
                : { duration: 0.8, repeat: Infinity, ease: "easeInOut" }
            }
            className="inline-block ml-1 w-[3px] h-[0.85em] bg-amber-500 dark:bg-amber-300 rounded-full align-middle select-none not-sr-only"
            style={{ WebkitTextFillColor: "initial" }}
          />
        )}
      </span>
    </h2>
  )
}

