"use client"

import React, { useState, useEffect, useRef } from "react"
import { motion, useInView, useReducedMotion } from "framer-motion"
import { cn } from "@/lib/utils"

export interface TypewriterHeadingProps {
  /** 欲打字輸出的完整字串 */
  text: string
  /** HTML 語意標籤，預設為 h3 */
  as?: "h1" | "h2" | "h3" | "h4" | "span" | "div"
  /** 容器額外樣式 */
  className?: string
  /** 每個字元敲入間隔 (ms)，預設 75ms */
  charDelay?: number
  /** 打完後游標淡出延遲 (ms)，預設 400ms */
  cursorFadeDelay?: number
}

export function TypewriterHeading(props: TypewriterHeadingProps) {
  return (
    <TypewriterHeadingContent
      key={`${props.as ?? "h3"}::${props.text}`}
      {...props}
    />
  )
}

function TypewriterHeadingContent({
  text,
  as: Component = "h3",
  className,
  charDelay = 75,
  cursorFadeDelay = 400,
}: TypewriterHeadingProps) {
  const containerRef = useRef<HTMLElement | null>(null)
  const hasStartedRef = useRef(false)
  const shouldReduceMotion = useReducedMotion()
  const isInView = useInView(containerRef, {
    once: false,
    margin: "-5% 0px -5% 0px",
  })

  const [charIndex, setCharIndex] = useState(0)
  const [isTypingComplete, setIsTypingComplete] = useState(false)
  const [cursorVisible, setCursorVisible] = useState(true)

  useEffect(() => {
    if (shouldReduceMotion || !isInView || hasStartedRef.current) {
      return
    }

    hasStartedRef.current = true
    let currentIndex = 0
    let fadeTimer: NodeJS.Timeout | null = null

    const interval = setInterval(() => {
      currentIndex += 1
      setCharIndex(currentIndex)

      if (currentIndex >= text.length) {
        clearInterval(interval)
        setIsTypingComplete(true)

        // 打字完成後延遲淡出游標
        fadeTimer = setTimeout(() => {
          setCursorVisible(false)
        }, cursorFadeDelay)
      }
    }, charDelay)

    return () => {
      clearInterval(interval)
      if (fadeTimer) clearTimeout(fadeTimer)
    }
  }, [isInView, text, charDelay, cursorFadeDelay, shouldReduceMotion])

  const displayedText = shouldReduceMotion ? text : text.slice(0, charIndex)
  const showCursor = !shouldReduceMotion && cursorVisible

  const innerContent = (
    <>
      {/* 1. a11y & SEO 完整文字 (視覺隱藏，螢幕閱讀器與搜尋引擎零延遲讀取) */}
      <span className="sr-only">{text}</span>

      {/* 2. 視覺打字逐字浮現層 (whitespace-pre-wrap 防範 375px 行動端溢位) */}
      <span aria-hidden="true" className="inline-block whitespace-pre-wrap">
        {displayedText}
      </span>

      {/* 3. 翠綠色微閃爍光標 (打字完成後自然平滑淡出) */}
      {showCursor && (
        <motion.span
          aria-hidden="true"
          initial={{ opacity: 1 }}
          animate={
            isTypingComplete
              ? { opacity: 0 }
              : { opacity: [1, 0, 1] }
          }
          transition={
            isTypingComplete
              ? { duration: 0.4, ease: "easeOut" }
              : { duration: 0.8, repeat: Infinity, ease: "easeInOut" }
          }
          className="inline-block ml-1 w-[2px] h-[0.9em] bg-emerald-500 dark:bg-emerald-400 rounded-full align-middle select-none"
        />
      )}
    </>
  )

  const combinedClass = cn("relative flex items-center py-0.5", className)

  if (Component === "h1") {
    return (
      <h1 ref={containerRef as React.RefObject<HTMLHeadingElement>} className={combinedClass}>
        {innerContent}
      </h1>
    )
  }
  if (Component === "h2") {
    return (
      <h2 ref={containerRef as React.RefObject<HTMLHeadingElement>} className={combinedClass}>
        {innerContent}
      </h2>
    )
  }
  if (Component === "h4") {
    return (
      <h4 ref={containerRef as React.RefObject<HTMLHeadingElement>} className={combinedClass}>
        {innerContent}
      </h4>
    )
  }
  if (Component === "span") {
    return (
      <span ref={containerRef as React.RefObject<HTMLSpanElement>} className={combinedClass}>
        {innerContent}
      </span>
    )
  }
  if (Component === "div") {
    return (
      <div ref={containerRef as React.RefObject<HTMLDivElement>} className={combinedClass}>
        {innerContent}
      </div>
    )
  }

  return (
    <h3 ref={containerRef as React.RefObject<HTMLHeadingElement>} className={combinedClass}>
      {innerContent}
    </h3>
  )
}
