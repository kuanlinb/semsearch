"""What an app is for, so "note-taking app" or "take a screenshot" can find it.

Each .app gets one short description, indexed like a document's text:
a curated line for common apps, otherwise its App Store category and the
file types it says it opens (from Info.plist).
"""
import plistlib
from pathlib import Path

# bundle id -> what people use the app for (short, plain words; search matches meaning)
KNOWN = {
    # macOS
    "com.apple.Notes": "take notes, notebook, memos, checklists",
    "com.apple.Stickies": "sticky notes on the desktop, quick memos",
    "com.apple.reminders": "reminders, to-do list, tasks, checklists",
    "com.apple.iCal": "calendar, events, meetings, schedule",
    "com.apple.mail": "email, inbox, send and read mail",
    "com.apple.MobileSMS": "text messages, iMessage, chat",
    "com.apple.FaceTime": "video calls, audio calls",
    "com.apple.mobilephone": "phone calls from your iPhone",
    "com.apple.AddressBook": "contacts, address book, phone numbers",
    "com.apple.Safari": "web browser, browse websites",
    "com.apple.Photos": "photo library, edit photos, albums",
    "com.apple.Preview": "view and annotate PDFs and images, sign documents",
    "com.apple.screenshot.launcher": "take a screenshot, record the screen, screen capture",
    "com.apple.QuickTimePlayerX": "play videos, record the screen, trim video",
    "com.apple.iMovieApp": "edit videos, make movies, trailers",
    "com.apple.garageband10": "make music, record audio, podcasts, instruments",
    "com.apple.Music": "music player, songs, playlists",
    "com.apple.podcasts": "listen to podcasts",
    "com.apple.TV": "watch movies and TV shows",
    "com.apple.iBooksX": "read ebooks and PDFs, audiobooks",
    "com.apple.news": "news articles",
    "com.apple.stocks": "stock prices, market watchlist",
    "com.apple.weather": "weather forecast",
    "com.apple.Maps": "maps, directions, navigation",
    "com.apple.findmy": "find a lost device, locate iPhone or AirPods, share location",
    "com.apple.Home": "smart home, lights, HomeKit devices",
    "com.apple.calculator": "calculator, arithmetic, unit conversion",
    "com.apple.clock": "clock, timer, alarm, stopwatch, world time",
    "com.apple.Dictionary": "dictionary, thesaurus, look up a word",
    "com.apple.TextEdit": "simple text editor, plain text and rich text documents",
    "com.apple.iWork.Pages": "word processor, write documents, letters, reports",
    "com.apple.iWork.Numbers": "spreadsheets, tables, budgets, charts",
    "com.apple.iWork.Keynote": "presentations, slides, slideshow",
    "com.apple.freeform": "whiteboard, brainstorming canvas, sketch ideas",
    "com.apple.journal": "journal, diary, daily writing",
    "com.apple.VoiceMemos": "voice recorder, record audio, voice memos",
    "com.apple.PhotoBooth": "take selfies and photos with the webcam",
    "com.apple.Image_Capture": "import photos from a camera or iPhone, scan documents",
    "com.apple.Passwords": "passwords, logins, passkeys, verification codes",
    "com.apple.systempreferences": "system settings, preferences, Wi-Fi, display, privacy",
    "com.apple.AppStore": "download and update apps",
    "com.apple.shortcuts": "automation, shortcuts, workflows",
    "com.apple.Automator": "automate repetitive tasks, workflows",
    "com.apple.Terminal": "command line, shell, terminal",
    "com.apple.ActivityMonitor": "see running processes, CPU and memory usage, force quit",
    "com.apple.DiskUtility": "format and repair disks, partitions, external drives",
    "com.apple.Console": "system logs, crash reports",
    "com.apple.SystemProfiler": "hardware and system information",
    "com.apple.FontBook": "install and manage fonts",
    "com.apple.ScreenSharing": "control another Mac remotely, screen sharing",
    "com.apple.ScreenContinuity": "use your iPhone from the Mac, iPhone mirroring",
    "com.apple.backup.launcher": "back up the Mac, restore files, Time Machine",
    "com.apple.MigrateAssistant": "move data from an old Mac or PC",
    "com.apple.DigitalColorMeter": "color picker, measure screen colors",
    "com.apple.grapher": "plot math functions, graphs",
    "com.apple.ScriptEditor2": "AppleScript editor",
    "com.apple.games": "games",
    "com.apple.Chess": "chess game",
    "com.apple.Magnifier": "magnifier, zoom in with the camera",
    "com.apple.printcenter": "printers, print queue",
    "com.apple.helpviewer": "tips and help for macOS",
    "com.apple.GenerativePlaygroundApp": "generate images with AI",
    # third-party
    "notion.id": "notes, docs, wiki, tasks, project planning",
    "com.goodnotesapp.x": "handwritten notes, notebooks, annotate PDFs",
    "com.microsoft.onenote.mac": "take notes, notebooks",
    "md.obsidian": "markdown notes, knowledge base, linked notes",
    "net.shinyfrog.bear": "markdown notes",
    "com.evernote.Evernote": "take notes, web clipper",
    "abnerworks.Typora": "markdown editor",
    "com.coderforart.One-Markdown": "markdown editor",
    "com.TickTick.task.mac": "to-do list, tasks, reminders, habit tracker",
    "com.culturedcode.ThingsMac": "to-do list, tasks, projects",
    "com.todoist.mac.Todoist": "to-do list, tasks",
    "com.microsoft.Word": "word processor, write documents, docx",
    "com.microsoft.Excel": "spreadsheets, tables, xlsx, formulas, charts",
    "com.microsoft.Powerpoint": "presentations, slides, pptx",
    "com.microsoft.Outlook": "email, calendar, contacts",
    "com.microsoft.teams2": "work chat, video meetings, calls",
    "us.zoom.xos": "video meetings, video calls, screen sharing",
    "com.tencent.tencentmeeting": "video meetings, video calls",
    "com.cisco.webexmeetingsapp": "video meetings",
    "com.tinyspeck.slackmacgap": "work chat, team messaging",
    "com.hnc.Discord": "chat, voice channels, communities",
    "jp.naver.line.mac": "chat, messaging, calls",
    "com.tencent.xinWeChat": "chat, messaging, calls",
    "net.whatsapp.WhatsApp": "chat, messaging, calls",
    "ru.keepcoder.Telegram": "chat, messaging",
    "org.mozilla.thunderbird": "email client",
    "com.google.Chrome": "web browser",
    "org.mozilla.firefox": "web browser",
    "com.microsoft.edgemac": "web browser",
    "company.thebrowser.Browser": "web browser",
    "com.brave.Browser": "web browser",
    "com.duckduckgo.macos.browser": "private web browser",
    "org.ecosia.browser": "web browser",
    "org.torproject.torbrowser": "anonymous web browser",
    "com.openai.atlas": "web browser with AI assistant",
    "com.openai.chat": "AI chatbot, ask questions",
    "com.openai.codex": "AI coding assistant",
    "com.anthropic.claudefordesktop": "AI assistant, chat, write and code",
    "com.google.GeminiMacOS": "AI assistant, chat",
    "com.microsoft.VSCode": "code editor, programming, IDE",
    "com.todesktop.230313mzl4w4u92": "AI code editor, programming",
    "com.google.antigravity-ide": "AI code editor, programming",
    "com.jetbrains.pycharm": "Python IDE, programming",
    "com.apple.dt.Xcode": "build apps for iPhone and Mac, IDE",
    "com.docker.docker": "containers, Docker",
    "com.github.GitHubClient": "git, GitHub",
    "org.spyder-ide.Spyder": "Python IDE, data science",
    "com.spotify.client": "music streaming, songs, playlists, podcasts",
    "com.netflix.Netflix": "watch movies and series",
    "org.videolan.vlc": "play any video or audio file",
    "com.colliderli.iina": "video player",
    "com.obsproject.obs-studio": "record the screen, live streaming",
    "com.movavi.videoconverter24": "convert video formats",
    "com.smoothmobile.mTheVideoConverter": "convert video formats",
    "com.canva.canvaeditor": "graphic design, posters, social media images, presentations",
    "com.figma.Desktop": "UI design, prototypes",
    "com.adobe.Photoshop": "edit photos, image editing",
    "com.adobe.illustrator": "vector graphics, illustration",
    "com.adobe.Acrobat.Pro": "edit and sign PDFs",
    "com.readdle.PDFExpert-Mac": "edit and annotate PDFs",
    "com.image.converter.heic.convert.photos.jpg.png.jpeg": "convert HEIC photos to JPG or PNG",
    "com.getdropbox.dropbox": "cloud storage, sync files",
    "com.google.drivefs": "Google Drive, cloud storage, sync files",
    "com.microsoft.OneDrive-mac": "OneDrive, cloud storage, sync files",
    "com.baidu.netdisk": "cloud storage, download files",
    "com.bitwarden.desktop": "password manager",
    "com.1password.1password": "password manager",
    "com.agilebits.onepassword7": "password manager",
    "com.teamviewer.TeamViewer": "remote control another computer, remote desktop",
    "com.carriez.rustdesk": "remote desktop",
    "com.deskin.client": "remote desktop",
    "com.microsoft.rdc.macos": "remote desktop to Windows",
    "io.tailscale.ipn.macsys": "VPN, private network between devices",
    "com.urban-vpn.mac": "VPN",
    "net.pulsesecure.Pulse-Secure": "work VPN",
    "com.ABabe.thearchiver": "unzip, extract RAR and ZIP archives",
    "com.Ababe.UnzipAnyFile": "unzip, extract RAR, ZIP and 7Z archives",
    "com.if.Amphetamine": "keep the Mac awake, prevent sleep",
    "com.jordanbaird.Ice": "hide menu bar icons",
    "com.valvesoftware.steam": "PC games store",
    "com.now.gg.BlueStacks": "run Android apps and games",
    "com.tableausoftware.tableaudesktop": "data visualization, dashboards, charts",
    "com.tradingview.tradingviewapp.desktop": "stock charts, trading",
    "org.idrix.VeraCrypt": "encrypt disks and files",
    "com.logi.optionsplus": "configure Logitech mouse and keyboard",
    "com.blackmagic-design.DiskSpeedTest": "test disk speed",
}

CATEGORY = {
    "productivity": "productivity", "utilities": "utility", "developer-tools": "developer tool, programming",
    "social-networking": "chat, social", "video": "video", "music": "music, audio", "finance": "finance, money, banking",
    "healthcare-fitness": "health, fitness", "business": "business, work", "entertainment": "entertainment",
    "education": "education, learning", "graphics-design": "graphic design", "books": "reading, books",
    "games": "games", "board-games": "board games", "reference": "reference", "travel": "travel",
    "news": "news", "photography": "photos, photography", "weather": "weather", "lifestyle": "lifestyle",
    "sports": "sports", "medical": "medical", "navigation": "maps, navigation",
}


def describe(path):
    """One line saying what the app does, or "" when there is nothing to go on."""
    try:
        with open(Path(path) / "Contents" / "Info.plist", "rb") as f:
            info = plistlib.load(f)
    except Exception:
        return ""
    known = KNOWN.get(info.get("CFBundleIdentifier", ""))
    if known:
        return known
    parts = []
    cat = str(info.get("LSApplicationCategoryType", "")).rsplit(".", 1)[-1]
    if cat in CATEGORY:
        parts.append(CATEGORY[cat])
    kinds = []
    for t in info.get("CFBundleDocumentTypes", []) or []:
        name = t.get("CFBundleTypeName") if isinstance(t, dict) else None
        if name and name not in kinds and not name.startswith(("public.", "com.", "org.")):
            kinds.append(name)
    if kinds:
        parts.append("opens " + ", ".join(kinds[:6]))
    return "; ".join(parts)
