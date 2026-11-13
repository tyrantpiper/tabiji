export type OfficialLanguage = "zh" | "en"

export interface WaypointInfo {
  id: string
  name: string
  en: string
  flag: string
  code: string
  x: number
  y: number
  tz: string
  distance: string
  distanceEn: string
  tag: string
  tagEn: string
}

export const WAYPOINTS_DATA: WaypointInfo[] = [
  {
    id: "taipei",
    name: "台北",
    en: "Taipei",
    flag: "🇹🇼",
    code: "TPE",
    x: 380,
    y: 195,
    tz: "UTC+8",
    distance: "核心協調起點",
    distanceEn: "Core Hub Origin",
    tag: "亞洲智慧協調樞紐",
    tagEn: "Asia Coordination Hub",
  },
  {
    id: "tokyo",
    name: "東京",
    en: "Tokyo",
    flag: "🇯🇵",
    code: "HND",
    x: 440,
    y: 130,
    tz: "UTC+9",
    distance: "+2,180 km",
    distanceEn: "+2,180 km",
    tag: "都會漫遊與鐵道接駁",
    tagEn: "Urban Transit & Metro Sync",
  },
  {
    id: "reykjavik",
    name: "雷克雅維克",
    en: "Reykjavik",
    flag: "🇮🇸",
    code: "KEF",
    x: 130,
    y: 65,
    tz: "UTC+0",
    distance: "+8,700 km",
    distanceEn: "+8,700 km",
    tag: "北極圈極光與冰原航線",
    tagEn: "Arctic Aurora & Glacier Path",
  },
  {
    id: "paris",
    name: "巴黎",
    en: "Paris",
    flag: "🇫🇷",
    code: "CDG",
    x: 200,
    y: 110,
    tz: "UTC+1",
    distance: "+9,800 km",
    distanceEn: "+9,800 km",
    tag: "歐洲跨城鐵路樞紐",
    tagEn: "European High-Speed Rail Hub",
  },
  {
    id: "newyork",
    name: "紐約",
    en: "New York",
    flag: "🇺🇸",
    code: "JFK",
    x: 80,
    y: 175,
    tz: "UTC-5",
    distance: "+12,500 km",
    distanceEn: "+12,500 km",
    tag: "跨大西洋跨時區漫遊",
    tagEn: "Transatlantic Cross-Zone Path",
  },
]

export interface MockDeviceDictionary {
  subHeader: {
    brand: string
    taglinePass: string
    taglineRoute: string
    taglineLedger: string
  }
  routeMode: {
    brandHeader: string
    heading: string
    btnNew: string
    btnJoin: string
    myTrips: string
    card1Badge: string
    card1Title: string
    card1Action: string
    card2Title: string
    card2Author: string
  }
  passMode: {
    tripDuration: string
    dayAll: string
    weatherLocation: string
    weatherDesc: string
    weatherStatus: string
    offlineBanner: string
    offlineLatency: string
    boardingPass: {
      flight: string
      class: string
      originLabel: string
      originValue: string
      destLabel: string
      destValue: string
      passSub: string
    }
    timeline1: { title: string; tag: string; desc: string }
    transit1: string
    timeline2: { title: string; tag: string; desc: string }
    timeline3: { title: string; tag: string; desc: string }
    storageStatus: string
    syncStatus: string
    mapPinBadge: string
  }
  ledgerMode: {
    badge: string
    title: string
    tabs: { cards: string; ledger: string; calc: string }
    filterTotal: string
    filterList: string
    filterAll: string
    filterPublic: string
    filterPrivate: string
    summaryTitle: string
    summaryPerPerson: string
    summaryTotal: string
    item1: { title: string; meta: string }
    item2: { title: string; meta: string }
    item3: { title: string; meta: string }
    btnAdd: string
  }
  dock: {
    arrival: string
    transit: string
    split: string
    profile: string
  }
}

export interface OfficialDictionary {
  nav: {
    experience: string
    routes: string
    offline: string
    ledger: string
    launchApp: string
    launchAppLong: string
    openMenu: string
    closeMenu: string
    homeAria: string
  }
  hero: {
    badge: string
    line1: string
    line2: string
    subtitle: string
    ctaLaunch: string
    ctaExplore: string
    trustPill1Title: string
    trustPill1Desc: string
    trustPill2Title: string
    trustPill2Desc: string
    trustPill3Title: string
    trustPill3Desc: string
  }
  theater: {
    badge: string
    heading: string
    subtitle: string
    modes: {
      pass: string
      route: string
      ledger: string
    }
    statusLive: string
    statusPausedHover: string
    statusPausedManual: string
    play: string
    pause: string
    playAria: string
    pauseAria: string
  }
  bento: {
    badge: string
    heading: string
    subtitle: string
    routes: {
      synced: string
      title: string
      subtitle: string
      tag: string
      desc: string
      ready: string
      selectWaypoint: string
    }
    offline: {
      title: string
      subtitle: string
      desc: string
      flightMode: string
      onlineMode: string
      toOfflineAria: string
      toOnlineAria: string
      latency: string
      offlineStatus: string
      onlineStatus: string
      zeroLatency: string
      syncStatus: string
      indexedDb: string
      indexedDbDesc: string
      serviceWorker: string
      serviceWorkerDesc: string
    }
    ledger: {
      synced: string
      title: string
      subtitle: string
      desc: string
      splitFour: string
      totalGroup: string
      toTotalAria: string
      toSplitAria: string
      perPerson: string
      totalAmount: string
      rateNote: string
    }
  }
  craft: {
    badge: string
    heading: string
    subtitle: string
    pillars: readonly {
      num: string
      title: string
      desc: string
    }[]
  }
  cta: {
    badge: string
    heading: string
    subtitle: string
    launch: string
    launchAria: string
    terms: string
    termsAria: string
  }
  footer: {
    desc: string
    navTitle: string
    routes: string
    offline: string
    ledger: string
    legalTitle: string
    terms: string
    privacy: string
    backApp: string
    disclaimer: string
    copyright: string
  }
  langSwitcher: {
    zh: string
    en: string
    ariaLabel: string
  }
  mockDevice: MockDeviceDictionary
}

export const officialTranslations: Record<OfficialLanguage, OfficialDictionary> = {
  zh: {
    nav: {
      experience: "行旅體驗",
      routes: "航線巡航",
      offline: "離線引擎",
      ledger: "智慧分帳",
      launchApp: "啟動應用",
      launchAppLong: "啟動應用 (Launch App)",
      openMenu: "開啟選單",
      closeMenu: "關閉選單",
      homeAria: "Tabiji 官方網站首頁",
    },
    hero: {
      badge: "自由行隨身夥伴 · 離線優先架構",
      line1: "走過的路，",
      line2: "都在這裡發光。",
      subtitle:
        "每一次出發，都是最純粹的冒險。跨時區航班自動理順、沒網路的山裡依然隨身查、多人吃飯各國匯率一秒算清。你的旅程，只屬於你。",
      ctaLaunch: "啟動應用",
      ctaExplore: "探索特色",
      trustPill1Title: "深山機艙隨身看",
      trustPill1Desc: "100% 離線一秒開行程",
      trustPill2Title: "跨國飛行不慌張",
      trustPill2Desc: "自動對齊當地時區與接駁",
      trustPill3Title: "足跡只屬於你",
      trustPill3Desc: "零廣告追蹤",
    },
    theater: {
      badge: "真實行旅狀態機 · 3 大極限時刻",
      heading: "握在掌心的，是整座城市的從容",
      subtitle:
        "無需等待下載或安裝肥大 App。落地斷網、地鐵穿行或餐後拆帳，Tabiji 在 3 大極限時刻始終平穩如初。",
      modes: {
        pass: "【斷網抵達】離線秒開",
        route: "【地鐵穿行】向量航線",
        ledger: "【餐後分帳】精準平攤",
      },
      statusLive: "實機功能動態展示",
      statusPausedHover: "已暫停播放 (移開繼續)",
      statusPausedManual: "已暫停播放 (點擊繼續)",
      play: "繼續",
      pause: "暫停",
      playAria: "繼續自動輪播",
      pauseAria: "暫停自動輪播",
    },
    bento: {
      badge: "輕裝出發 · 核心行旅能力",
      heading: "為旅行而生，每一步都自在從容",
      subtitle:
        "把複雜的時區、訊號與算帳留給 Tabiji；你只要負責享受迎面吹來的風，和眼前最美的那道風景。",
      routes: {
        synced: "✦ Global Waypoints Synced",
        title: "空間航線巡航",
        subtitle: "跨時區飛行，每一步都清晰從容",
        tag: "5 大洲航點",
        desc: "起飛、轉機到落地，自動對齊當地時間與接駁；即便在萬米高空，旅程節奏依舊明明白白。",
        ready: "離線就緒",
        selectWaypoint: "選擇航點",
      },
      offline: {
        title: "離線自癒引擎",
        subtitle: "深山機艙沒訊號？全球行程隨手秒開",
        desc: "深山荒野、高空飛行或地下鐵，完全沒有網路也能一秒打開行程與地圖。把世界妥妥裝進手機，每一步都踏實安心。",
        flightMode: "✈️ 飛航深山模式",
        onlineMode: "📶 全球高速連網",
        toOfflineAria: "切換至模擬斷網模式",
        toOnlineAria: "切換至在線模式",
        latency: "讀取延遲",
        offlineStatus: "✈️ 飛航深山模式 · Airplane Mode · Local Snapshot Engaged",
        onlineStatus: "📶 城市高速連線 · Edge CDN Active · Ping 18ms",
        zeroLatency: "0 延遲本地秒開",
        syncStatus: "雙向增量同步",
        indexedDb: "手機本機快照 (IndexedDB)",
        indexedDbDesc: "100% 離線可用",
        serviceWorker: "背景預載就緒 (Service Worker)",
        serviceWorkerDesc: "精準快取防護",
      },
      ledger: {
        synced: "✦ Real-Time Multi-Currency",
        title: "智慧多幣別分帳",
        subtitle: "結帳不手忙腳亂，各國幣別一秒算清",
        desc: "各國貨幣一鍵自動換算，4人平攤或全團結算瞬間算清，把算帳的時間留給下一個景點。",
        splitFour: "4人精準平攤",
        totalGroup: "全團總額",
        toTotalAria: "切換為全團總額",
        toSplitAria: "切換為4人平攤",
        perPerson: "每人應付份額 (4人均攤)",
        totalAmount: "本趟行程總計費用",
        rateNote: "基於即時中價匯率自動折算",
      },
    },
    craft: {
      badge: "Thoughtful Craft · 專注行旅本質",
      heading: "在陌生的遠方，每一步都踏實從容",
      subtitle:
        "沒有繁瑣的設定，不帶來多餘的干擾。Tabiji 把複雜的連線、計算與隱私防護留給幕後，讓你在斷網、換匯與旅伴相處的關鍵時刻，始終保有最純粹的旅行節奏。",
      pillars: [
        {
          num: "01 · 斷網隨行",
          title: "無網之境，行程依然隨身",
          desc: "落地開航模、深山荒野或深入地下鐵，即使完全沒有訊號，所有行程細節與離線地圖依然隨點即開，告別斷網焦慮。",
        },
        {
          num: "02 · 智慧分帳",
          title: "多幣別平攤，優雅結算",
          desc: "即時換算多國匯率，餐後 3 秒精準拆帳。每筆公私花費清楚明瞭，旅伴同行不再為算錢煩惱，體面又省心。",
        },
        {
          num: "03 · 隱私守護",
          title: "你的足跡，只屬於你",
          desc: "堅持零廣告追蹤、不嵌入第三方追蹤代碼。你踏過的每一座城市與私房足跡，永遠完整保留在你的手機裡。",
        },
        {
          num: "04 · 安心同行",
          title: "公開透明，誠實守護",
          desc: "以嚴謹清楚的服務準則與隱私規範為基石，尊重每位旅人的自主權，為每一次出發提供踏實而值得信賴的後盾。",
        },
      ],
    },
    cta: {
      badge: "無須註冊 · 開箱即用 · 離線保全",
      heading: "準備好出發了嗎？下一站，就在眼前。",
      subtitle: "開啟 Tabiji，把行程、地圖與花費一次理順，帶著最放鬆的心情走向世界。",
      launch: "開啟我的旅程",
      launchAria: "立即啟動 Tabiji (Launch App)",
      terms: "查閱條款",
      termsAria: "查閱服務條款",
    },
    footer: {
      desc: "探索世界，絲滑無界。專為全球自由行旅人打造的高工藝行旅作業系統，具備極限斷網離線自癒、動態空間航線牽引與多幣別即時分帳精算。",
      navTitle: "功能導航",
      routes: "航線巡航 (Spatial Routes)",
      offline: "離線引擎 (Offline Engine)",
      ledger: "智慧分帳 (Multi-Currency)",
      legalTitle: "法律條款中心",
      terms: "服務條款 (Terms of Service)",
      privacy: "隱私權政策 (Privacy Policy)",
      backApp: "返回主應用 (Launch Tabiji)",
      disclaimer:
        "免責聲明：Tabiji 旅路為獨立旅遊協調工具，AI 產生之行程、即時天氣預報與路線估算僅供出行規劃參考，實際路況與營業時間請依各官方公告為準。",
      copyright: "© 2026 Tabiji (旅路). All rights reserved. 獨立全端行旅工藝。",
    },
    langSwitcher: {
      zh: "繁中",
      en: "EN",
      ariaLabel: "語系切換 (Language Switcher)",
    },
    mockDevice: {
      subHeader: {
        brand: "TABIJI • 旅路",
        taglinePass: "【斷網抵達】離線時間軸秒開",
        taglineRoute: "【地鐵穿行】零等待向量航線",
        taglineLedger: "【餐後分帳】居酒屋精準平攤",
      },
      routeMode: {
        brandHeader: "TABIJI・旅路",
        heading: "管理您的旅程",
        btnNew: "建立新旅程",
        btnJoin: "加入行程",
        myTrips: "我的行程 (2)",
        card1Badge: "🎓 範例",
        card1Title: "3 Day Taipei Explorer ✨",
        card1Action: "點擊探索 →",
        card2Title: "東京 5 日自由行行程表",
        card2Author: "By Ryan",
      },
      passMode: {
        tripDuration: "3 天 2 晚",
        dayAll: "ALL 總覽",
        weatherLocation: "台北 101",
        weatherDesc: "18°C 晴朗天候 · 降雨機率 10%",
        weatherStatus: "即時連線",
        offlineBanner: "100% 離線可用 · 本地自癒快照",
        offlineLatency: "0ms 延遲",
        boardingPass: {
          flight: "FLIGHT TB-2026",
          class: "FIRST CLASS",
          originLabel: "ORIGIN",
          originValue: "CURRENT SPOT",
          destLabel: "DESTINATION",
          destValue: "EVERYWHERE",
          passSub: "護照與國際機票 (100% 離線快取憑證)",
        },
        timeline1: {
          title: "台北 101 觀景台",
          tag: "門票 NT$600",
          desc: "89F 全景高空漫步 · 遠眺台北天際線",
        },
        transit1: "🚶 步行 3 分鐘 (信義天橋連通廊道)",
        timeline2: {
          title: "鼎泰豐 101 店",
          tag: "必比登推薦",
          desc: "經典小籠包與蝦仁燒賣 · 建議 11:30 前候位",
        },
        timeline3: {
          title: "象山步道 · 巨石觀景台",
          tag: "黃金日落",
          desc: "登頂遠眺信義天際線，夜景絕美攝影熱點",
        },
        storageStatus: "IndexedDB 本地儲存：5.2 MB",
        syncStatus: "已同步完整資料",
        mapPinBadge: "當日地圖 5 處",
      },
      ledgerMode: {
        badge: "工具箱",
        title: "工具 · 記帳與 AI 工具",
        tabs: {
          cards: "卡片",
          ledger: "記帳",
          calc: "精算器",
        },
        filterTotal: "總計",
        filterList: "列表",
        filterAll: "全部",
        filterPublic: "公帳",
        filterPrivate: "私帳",
        summaryTitle: "公帳分攤總覽",
        summaryPerPerson: "平均每人應付 (3人平攤)",
        summaryTotal: "全團總支出 NT$ 12,850 · 約 ¥59,767",
        item1: {
          title: "跨國特色饗宴 (鼎泰豐)",
          meta: "晚餐 · 3人均分",
        },
        item2: {
          title: "高鐵與城際接駁通行",
          meta: "交通 · Ryan 先行墊付",
        },
        item3: {
          title: "景觀設計精品旅宿",
          meta: "住宿 2 晚 · 公帳扣款",
        },
        btnAdd: "新增支出項目",
      },
      dock: {
        arrival: "抵達",
        transit: "穿行",
        split: "分帳",
        profile: "個人",
      },
    },
  },
  en: {
    nav: {
      experience: "Experience",
      routes: "Spatial Routes",
      offline: "Offline Engine",
      ledger: "Smart Ledger",
      launchApp: "Launch App",
      launchAppLong: "Launch App ↗",
      openMenu: "Open Menu",
      closeMenu: "Close Menu",
      homeAria: "Tabiji Official Portal Home",
    },
    hero: {
      badge: "Independent Travel Companion · Offline-First Architecture",
      line1: "Where every step,",
      line2: "finds its light.",
      subtitle:
        "Every departure is a pure adventure. Cross-timezone flights organized seamlessly, instant access in signal-free mountains, and multi-currency dinner splitting in seconds. Your journey belongs only to you.",
      ctaLaunch: "Launch App",
      ctaExplore: "Explore Features",
      trustPill1Title: "Mountains & Cabin Ready",
      trustPill1Desc: "100% Offline Instant Itinerary",
      trustPill2Title: "Calm Global Transit",
      trustPill2Desc: "Auto-aligned local time & transit",
      trustPill3Title: "Footprints Stay Yours",
      trustPill3Desc: "Zero tracking or profiling",
    },
    theater: {
      badge: "Authentic State Machine · 3 Extreme Moments",
      heading: "In your palm, the serenity of the city",
      subtitle:
        "No bloated app downloads required. Off-grid arrival, subway transit, or post-meal splitting—Tabiji stays rock-solid in every critical moment.",
      modes: {
        pass: "【Off-Grid Arrival】Instant Offline",
        route: "【Subway Transit】Vector Routes",
        ledger: "【Post-Meal Split】Fair Share",
      },
      statusLive: "Live Interactive Showcase",
      statusPausedHover: "Playback paused (Hover away to resume)",
      statusPausedManual: "Playback paused (Click to resume)",
      play: "Resume",
      pause: "Pause",
      playAria: "Resume auto rotation",
      pauseAria: "Pause auto rotation",
    },
    bento: {
      badge: "Travel Light · Core Travel Capabilities",
      heading: "Crafted for Travel, Confident Every Step",
      subtitle:
        "Leave complex time zones, offline sync, and group split math to Tabiji. Just embrace the breeze and savor the journey.",
      routes: {
        synced: "✦ Global Waypoints Synced",
        title: "Spatial Route Cruise",
        subtitle: "Global flights, crystal-clear across timezones",
        tag: "5 Continents Connected",
        desc: "From departure and layovers to landing, local time zones and connections sync automatically—even 30,000 feet in the air.",
        ready: "Offline Ready",
        selectWaypoint: "Select waypoint",
      },
      offline: {
        title: "Offline Self-Healing Engine",
        subtitle: "No signal in flight or woods? Instant access anywhere",
        desc: "Wild trails, high altitudes, or subterranean subways—access your full itinerary and maps with zero delay. Hold the world safely in your pocket.",
        flightMode: "✈️ Airplane Deep Mode",
        onlineMode: "📶 Global High-Speed Link",
        toOfflineAria: "Switch to simulated offline mode",
        toOnlineAria: "Switch to online mode",
        latency: "Read Latency",
        offlineStatus: "✈️ Airplane Mode · Local Snapshot Engaged",
        onlineStatus: "📶 Urban Fiber Network · Edge CDN Active · Ping 18ms",
        zeroLatency: "0ms Local Instant Access",
        syncStatus: "Two-way incremental sync",
        indexedDb: "Local On-Device Snapshot (IndexedDB)",
        indexedDbDesc: "100% available offline",
        serviceWorker: "Background Preload Active (Service Worker)",
        serviceWorkerDesc: "Precision cache protection",
      },
      ledger: {
        synced: "✦ Real-Time Multi-Currency",
        title: "Smart Multi-Currency Split",
        subtitle: "No checkout stress, instant cross-currency math",
        desc: "Instant real-time currency conversion. Split 4 ways or reconcile total trip spending in seconds. Spend your time on the next sight.",
        splitFour: "4-Way Split",
        totalGroup: "Group Total",
        toTotalAria: "Switch to group total",
        toSplitAria: "Switch to 4-way split",
        perPerson: "Per Person Share (4-Way Split)",
        totalAmount: "Total Trip Expenses",
        rateNote: "Calculated via live mid-market exchange rates",
      },
    },
    craft: {
      badge: "Thoughtful Craft · Focus on Pure Travel",
      heading: "In Unfamiliar Lands, Every Step Confident & Free",
      subtitle:
        "No tedious configurations, zero intrusive distractions. Tabiji handles synchronization, ledger conversions, and privacy in the background so you can enjoy pure travel serenity.",
      pillars: [
        {
          num: "01 · Offline Travel",
          title: "Signal-Free, Itinerary Stays In Pocket",
          desc: "Airplane mode, deep forests, or underground transit—all itinerary details and offline maps remain instantly accessible.",
        },
        {
          num: "02 · Smart Ledger",
          title: "Multi-Currency Split, Elegant Settlement",
          desc: "Real-time currency exchange rates and 3-second bill splitting. Clear personal and shared expenses keep travel harmonious.",
        },
        {
          num: "03 · Privacy Guard",
          title: "Your Footprints Belong Only To You",
          desc: "Zero ad tracking, zero telemetry injection. Every city alley and secret spot you visit stays entirely on your device.",
        },
        {
          num: "04 · Peace of Mind",
          title: "Open, Transparent, Trustworthy",
          desc: "Built on rigorous service guidelines and privacy principles, empowering independent travelers with a dependable foundation.",
        },
      ],
    },
    cta: {
      badge: "No Signup · Instant Start · 100% Offline Safe",
      heading: "Ready for your journey? Next stop is right ahead.",
      subtitle:
        "Open Tabiji to align your routes, maps, and expenses. Step into the world with absolute peace of mind.",
      launch: "Start My Journey",
      launchAria: "Launch Tabiji (Launch App)",
      terms: "Review Terms",
      termsAria: "Review Terms of Service",
    },
    footer: {
      desc: "Explore the world with seamless serenity. A high-craft travel operating system built for independent globetrotters—featuring resilient offline self-healing, dynamic spatial route navigation, and instant multi-currency group ledger.",
      navTitle: "Navigation",
      routes: "Spatial Routes",
      offline: "Offline Engine",
      ledger: "Smart Ledger",
      legalTitle: "Legal Center",
      terms: "Terms of Service",
      privacy: "Privacy Policy",
      backApp: "Launch Tabiji",
      disclaimer:
        "Disclaimer: Tabiji is an independent travel coordination companion. AI-generated itineraries, weather forecasts, and route estimates serve as travel planning references only.",
      copyright: "© 2026 Tabiji (旅路). All rights reserved. Crafted for independent travelers.",
    },
    langSwitcher: {
      zh: "繁中",
      en: "EN",
      ariaLabel: "Switch Language",
    },
    mockDevice: {
      subHeader: {
        brand: "TABIJI • TRAVEL",
        taglinePass: "【Off-Grid Arrival】Instant Timeline",
        taglineRoute: "【Subway Transit】Zero-Lag Vector Routes",
        taglineLedger: "【Post-Meal Split】Fair Share Calculation",
      },
      routeMode: {
        brandHeader: "TABIJI・TRAVEL",
        heading: "Manage your journeys",
        btnNew: "New Journey",
        btnJoin: "Join Trip",
        myTrips: "My Trips (2)",
        card1Badge: "🎓 Sample",
        card1Title: "3 Day Taipei Explorer ✨",
        card1Action: "Explore →",
        card2Title: "5-Day Tokyo Free Travel",
        card2Author: "By Ryan",
      },
      passMode: {
        tripDuration: "3 Days 2 Nights",
        dayAll: "ALL Overview",
        weatherLocation: "Taipei 101",
        weatherDesc: "18°C Sunny · 10% Rain",
        weatherStatus: "Live Sync",
        offlineBanner: "100% Offline Ready · Local Snapshot",
        offlineLatency: "0ms Latency",
        boardingPass: {
          flight: "FLIGHT TB-2026",
          class: "FIRST CLASS",
          originLabel: "ORIGIN",
          originValue: "CURRENT SPOT",
          destLabel: "DESTINATION",
          destValue: "EVERYWHERE",
          passSub: "Passport & Boarding Pass (100% Offline Verified)",
        },
        timeline1: {
          title: "Taipei 101 Observatory",
          tag: "Ticket NT$600",
          desc: "89F Panoramic Observatory · Taipei Skyline",
        },
        transit1: "🚶 3 min walk (Xinyi Skybridge corridor)",
        timeline2: {
          title: "Din Tai Fung 101",
          tag: "Bib Gourmand",
          desc: "Classic Xiao Long Bao & Shumai · Early wait advised",
        },
        timeline3: {
          title: "Elephant Mountain Trail · Boulder Lookout",
          tag: "Golden Sunset",
          desc: "Summit view of Xinyi skyline · Sunset photography spot",
        },
        storageStatus: "IndexedDB Local: 5.2 MB",
        syncStatus: "Full Data Synced",
        mapPinBadge: "5 Map Spots Today",
      },
      ledgerMode: {
        badge: "Toolbox",
        title: "Tools · Expenses & AI Tools",
        tabs: {
          cards: "Cards",
          ledger: "Expenses",
          calc: "Calculator",
        },
        filterTotal: "Total",
        filterList: "List",
        filterAll: "All",
        filterPublic: "Group",
        filterPrivate: "Personal",
        summaryTitle: "Group Split Overview",
        summaryPerPerson: "Average per person (3-way split)",
        summaryTotal: "Total Group Expenses NT$ 12,850 · Approx. ¥59,767",
        item1: {
          title: "Gourmet Dining (Din Tai Fung)",
          meta: "Dinner · 3-way split",
        },
        item2: {
          title: "HSR & Intercity Transit",
          meta: "Transit · Paid by Ryan",
        },
        item3: {
          title: "Boutique Design Hotel",
          meta: "Stay 2 Nights · Group funds",
        },
        btnAdd: "Add Expense",
      },
      dock: {
        arrival: "Arrival",
        transit: "Transit",
        split: "Split",
        profile: "Profile",
      },
    },
  },
}

export type OfficialTranslations = OfficialDictionary
