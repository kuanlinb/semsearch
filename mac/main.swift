// SemSearch: press ⌥Space for a Spotlight-like search box backed by the local search service.
import Carbon.HIToolbox
import Cocoa
import Quartz

// install.sh records where the Python project lives
let repoDir = Bundle.main.object(forInfoDictionaryKey: "SemSearchRepo") as? String
    ?? ProcessInfo.processInfo.environment["SEMSEARCH_REPO"] ?? NSHomeDirectory() + "/semsearch"

// UI language follows the system. Translations live in l10n/<lang>.json, keyed by the English text;
// a language without a file falls back to English.
let uiLang: String = {
    let parts = (Locale.preferredLanguages.first ?? "en").split(separator: "-").map(String.init)
    guard parts.first == "zh" else { return parts.first ?? "en" }
    return parts.contains("Hant") || ["TW", "HK", "MO"].contains(parts.last ?? "") ? "zh-Hant" : "zh-Hans"
}()
let strings: [String: String] = {
    guard let data = FileManager.default.contents(atPath: repoDir + "/l10n/\(uiLang).json") else { return [:] }
    return (try? JSONSerialization.jsonObject(with: data)) as? [String: String] ?? [:]
}()
func L(_ en: String, _ args: [String: Any] = [:]) -> String {
    var s = strings[en] ?? en
    for (k, v) in args { s = s.replacingOccurrences(of: "{\(k)}", with: "\(v)") }
    return s
}

// Port: SEMSEARCH_PORT, else "port" in ~/.semsearch/config.json, else 8799
let serverPort: Int = {
    if let p = ProcessInfo.processInfo.environment["SEMSEARCH_PORT"], let n = Int(p) { return n }
    let cfg = NSHomeDirectory() + "/.semsearch/config.json"
    if let d = FileManager.default.contents(atPath: cfg),
       let j = try? JSONSerialization.jsonObject(with: d) as? [String: Any], let n = j["port"] as? Int {
        return n
    }
    return 8799
}()
let serverURL = "http://127.0.0.1:\(serverPort)"

struct Hit: Decodable {
    let path: String
    let name: String
    let ext: String
    let is_dir: Bool
    let cloud: Bool
    let note: String
    let snippet: String
    let match: String
    let mtime: Double
    let copies: Int?
    let group: [Hit]?   // lower-ranked files from the same folder (Tab expands them)
}

struct SearchResponse: Decodable {
    let results: [Hit]
    let ms: Int
    let reranked: Bool?
}

// MARK: - Global hotkey (Carbon; needs no Accessibility permission)

final class HotKey {
    private var ref: EventHotKeyRef?
    private static var handler: (() -> Void)?

    init(keyCode: UInt32, modifiers: UInt32, action: @escaping () -> Void) {
        HotKey.handler = action
        var spec = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        InstallEventHandler(GetApplicationEventTarget(), { _, _, _ in
            HotKey.handler?()
            return noErr
        }, 1, &spec, nil, nil)
        let id = EventHotKeyID(signature: OSType(0x5353_4348), id: 1)  // "SSCH"
        RegisterEventHotKey(keyCode, modifiers, id, GetApplicationEventTarget(), 0, &ref)
    }
}

// MARK: - Search panel

final class KeyPanel: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { true }
}

// Liquid Glass (NSGlassEffectView) on macOS 26, frosted glass on older systems.
// Looked up by name so it still builds with older SDKs.
func makeGlass(radius: CGFloat) -> (outer: NSView, content: NSView) {
    let content = NSView()
    if let cls = NSClassFromString("NSGlassEffectView") as? NSView.Type {
        let g = cls.init(frame: .zero)
        g.setValue(content, forKey: "contentView")
        g.setValue(radius, forKey: "cornerRadius")
        return (g, content)
    }
    let v = NSVisualEffectView()
    v.material = .popover
    v.blendingMode = .behindWindow
    v.state = .active
    v.wantsLayer = true
    v.layer?.cornerRadius = radius
    v.layer?.masksToBounds = true
    content.translatesAutoresizingMaskIntoConstraints = false
    v.addSubview(content)
    NSLayoutConstraint.activate([
        content.leadingAnchor.constraint(equalTo: v.leadingAnchor), content.trailingAnchor.constraint(equalTo: v.trailingAnchor),
        content.topAnchor.constraint(equalTo: v.topAnchor), content.bottomAnchor.constraint(equalTo: v.bottomAnchor),
    ])
    return (v, content)
}

final class ResultCell: NSTableCellView {
    let icon = NSImageView()
    let title = NSTextField(labelWithString: "")
    let detail = NSTextField(labelWithString: "")
    let badge = NSTextField(labelWithString: "")

    lazy var indent: NSLayoutConstraint = icon.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 18)

    override init(frame: NSRect) {
        super.init(frame: frame)
        for v in [icon, title, detail, badge] {
            v.translatesAutoresizingMaskIntoConstraints = false
            addSubview(v)
        }
        title.font = .systemFont(ofSize: 14, weight: .medium)
        title.lineBreakMode = .byTruncatingMiddle
        detail.font = .systemFont(ofSize: 11.5)
        detail.lineBreakMode = .byTruncatingTail
        detail.maximumNumberOfLines = 1
        badge.font = .systemFont(ofSize: 11.5)
        badge.alignment = .right
        badge.setContentCompressionResistancePriority(.required, for: .horizontal)
        title.setContentCompressionResistancePriority(.defaultLow, for: .horizontal)
        NSLayoutConstraint.activate([
            indent,
            icon.centerYAnchor.constraint(equalTo: centerYAnchor),
            icon.widthAnchor.constraint(equalToConstant: 30),
            icon.heightAnchor.constraint(equalToConstant: 30),
            title.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 10),
            title.bottomAnchor.constraint(equalTo: centerYAnchor, constant: 1),
            title.trailingAnchor.constraint(lessThanOrEqualTo: badge.leadingAnchor, constant: -10),
            badge.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -20),
            badge.centerYAnchor.constraint(equalTo: centerYAnchor),
            detail.leadingAnchor.constraint(equalTo: title.leadingAnchor),
            detail.topAnchor.constraint(equalTo: centerYAnchor, constant: 2),
            detail.trailingAnchor.constraint(lessThanOrEqualTo: badge.leadingAnchor, constant: -10),
        ])
        recolor()
    }

    required init?(coder: NSCoder) { fatalError() }

    // The selected row is solid accent color with white text, like Spotlight
    override var backgroundStyle: NSView.BackgroundStyle { didSet { recolor() } }

    func recolor() {
        let on = backgroundStyle == .emphasized
        title.textColor = on ? .white : .labelColor
        detail.textColor = on ? NSColor.white.withAlphaComponent(0.85) : .secondaryLabelColor
        badge.textColor = on ? NSColor.white.withAlphaComponent(0.85) : .tertiaryLabelColor
    }

    func show(_ h: Hit, child: Bool = false, expanded: Bool = false) {
        indent.constant = child ? 46 : 18
        if h.path.hasSuffix("/.Trash") {
            icon.image = NSImage(named: NSImage.trashFullName) ?? NSWorkspace.shared.icon(forFile: h.path)
        } else {
            icon.image = NSWorkspace.shared.icon(forFile: h.path)
        }
        title.stringValue = h.name
        let home = NSHomeDirectory()
        var shortPath = h.path.hasPrefix(home) ? "~" + h.path.dropFirst(home.count) : h.path
        for (long, short) in [("~/Library/CloudStorage/", ""),
                              ("~/Library/Mobile Documents/com~apple~CloudDocs", "iCloud Drive")]
            where shortPath.hasPrefix(long) {
            shortPath = short + shortPath.dropFirst(long.count)
            break
        }
        let folder = (shortPath as NSString).deletingLastPathComponent
        if (h.match == "content" || h.match == "place") && !h.snippet.isEmpty {
            // Collapse table-of-contents dot leaders into one ellipsis
            detail.stringValue = h.snippet.replacingOccurrences(of: "\n", with: " ")
                .replacingOccurrences(of: "[.．·…\\s]{4,}", with: " … ", options: .regularExpression)
            detail.lineBreakMode = .byTruncatingTail
        } else {
            detail.stringValue = h.note.isEmpty ? folder : "\(folder) · \(L("contains")) \(h.note)"
            detail.lineBreakMode = .byTruncatingMiddle
        }
        toolTip = shortPath
        // Keep the right side quiet: same-folder count and date only; cloud/copies go in the tooltip
        var tags: [String] = []
        if !child, let g = h.group?.count, g > 0 { tags.append(expanded ? L("collapse") : L("+{n} in folder", ["n": g])) }
        if h.mtime > 0 { tags.append(ResultCell.dateText(h.mtime)) }
        badge.stringValue = tags.joined(separator: " · ")
    }

    // Time for today, month/day for this year, full date otherwise
    static func dateText(_ t: Double) -> String {
        let d = Date(timeIntervalSince1970: t)
        let cal = Calendar.current
        let df = DateFormatter()
        df.locale = Locale(identifier: Locale.preferredLanguages.first ?? "en")  // follow the UI language, not the region
        if cal.isDateInToday(d) { df.dateFormat = "HH:mm" }
        else if cal.isDateInYesterday(d) { return L("Yesterday") }
        else if cal.component(.year, from: d) == cal.component(.year, from: Date()) { df.setLocalizedDateFormatFromTemplate("MMMd") }
        else { df.dateFormat = "yyyy/M/d" }
        return df.string(from: d)
    }
}

final class RowView: NSTableRowView {
    // The search field keeps keyboard focus, so force the emphasized selection style
    override var isEmphasized: Bool { get { true } set {} }
    override func drawSelection(in dirtyRect: NSRect) {
        let r = bounds.insetBy(dx: 8, dy: 1)
        NSColor.controlAccentColor.setFill()
        NSBezierPath(roundedRect: r, xRadius: 10, yRadius: 10).fill()
    }
}

final class SearchController: NSObject, NSTextFieldDelegate, NSTableViewDataSource, NSTableViewDelegate, NSWindowDelegate {
    let panel: KeyPanel
    let field = NSTextField()
    let table = NSTableView()
    let scroll = NSScrollView()
    let footer = NSTextField(labelWithString: "")
    var hits: [Hit] = []          // rows on screen, including expanded same-folder files
    var heads: [Hit] = []         // results from the service (one per folder)
    var expanded = Set<String>()  // paths of the heads that are expanded
    var childPaths = Set<String>()

    func rebuild() {
        hits = []
        childPaths = []
        for h in heads {
            hits.append(h)
            if expanded.contains(h.path) {
                for g in h.group ?? [] {
                    hits.append(g)
                    childPaths.insert(g.path)
                }
            }
        }
    }

    // Tab: expand or collapse the other files from the selected result's folder
    func toggleGroup() {
        guard let h = selected else { return }
        let head = childPaths.contains(h.path)
            ? heads.first { ($0.group ?? []).contains { $0.path == h.path } }
            : h
        guard let head, !(head.group ?? []).isEmpty else { return }
        if expanded.contains(head.path) { expanded.remove(head.path) } else { expanded.insert(head.path) }
        rebuild()
        table.reloadData()
        if let i = hits.firstIndex(where: { $0.path == head.path }) {
            table.selectRowIndexes([i], byExtendingSelection: false)
            table.scrollRowToVisible(i)
        }
        setExpanded(true)
    }

    var pending: DispatchWorkItem?
    var pendingFine: DispatchWorkItem?
    var task: URLSessionDataTask?
    var fineTask: URLSessionDataTask?
    var cardHeight: NSLayoutConstraint!
    let width: CGFloat = 680
    let barH: CGFloat = 56
    let gap: CGFloat = 10
    let rowH: CGFloat = 50
    let maxRows = 8
    let hints = NSTextField(labelWithString: L("↩ open   ⌘↩ show in Finder   ⌘Y preview   Tab expand"))
    var card: NSView!
    var glassParts: [(outer: NSView, content: NSView)] = []  // for --snapshot

    override init() {
        panel = KeyPanel(contentRect: NSRect(x: 0, y: 0, width: 680, height: 56),
                         styleMask: [.borderless, .nonactivatingPanel, .fullSizeContentView],
                         backing: .buffered, defer: false)
        super.init()
        panel.isFloatingPanel = true
        panel.level = .modalPanel
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .transient]
        panel.backgroundColor = .clear
        panel.isOpaque = false
        panel.hasShadow = true
        panel.isMovableByWindowBackground = true
        panel.hidesOnDeactivate = false
        panel.delegate = self

        let root = NSView()
        panel.contentView = root
        let (bar, barContent) = makeGlass(radius: barH / 2)
        let (cardView, cardContent) = makeGlass(radius: 24)
        card = cardView
        glassParts = [(bar, barContent), (cardView, cardContent)]
        for v in [bar, cardView] {
            v.translatesAutoresizingMaskIntoConstraints = false
            root.addSubview(v)
        }

        let glyph = NSImageView(image: NSImage(systemSymbolName: "magnifyingglass", accessibilityDescription: nil)!)
        glyph.symbolConfiguration = .init(pointSize: 19, weight: .medium)
        glyph.contentTintColor = .secondaryLabelColor

        field.placeholderString = L("SemSearch: describe the file or app you are looking for")
        field.font = .systemFont(ofSize: 21, weight: .regular)
        field.isBordered = false
        field.drawsBackground = false
        field.focusRingType = .none
        field.delegate = self
        field.cell?.usesSingleLineMode = true
        field.cell?.isScrollable = true

        table.addTableColumn(NSTableColumn(identifier: .init("c")))
        table.headerView = nil
        table.rowHeight = rowH
        table.intercellSpacing = .zero
        table.backgroundColor = .clear
        table.selectionHighlightStyle = .regular
        table.dataSource = self
        table.delegate = self
        table.target = self
        table.doubleAction = #selector(openSelected)
        table.style = .plain
        scroll.documentView = table
        scroll.drawsBackground = false
        scroll.hasVerticalScroller = true
        scroll.scrollerStyle = .overlay
        scroll.automaticallyAdjustsContentInsets = false
        scroll.contentInsets = NSEdgeInsets(top: 8, left: 0, bottom: 4, right: 0)

        for f in [footer, hints] {
            f.font = .systemFont(ofSize: 11)
            f.textColor = .tertiaryLabelColor
        }
        hints.alignment = .right

        for (v, parent) in [(glyph, barContent), (field, barContent), (scroll, cardContent),
                            (footer, cardContent), (hints, cardContent)] as [(NSView, NSView)] {
            v.translatesAutoresizingMaskIntoConstraints = false
            parent.addSubview(v)
        }
        cardHeight = cardView.heightAnchor.constraint(equalToConstant: 100)
        NSLayoutConstraint.activate([
            bar.topAnchor.constraint(equalTo: root.topAnchor),
            bar.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            bar.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            bar.heightAnchor.constraint(equalToConstant: barH),
            bar.widthAnchor.constraint(equalToConstant: width),
            cardView.topAnchor.constraint(equalTo: bar.bottomAnchor, constant: gap),
            cardView.leadingAnchor.constraint(equalTo: root.leadingAnchor),
            cardView.trailingAnchor.constraint(equalTo: root.trailingAnchor),
            cardHeight,
            glyph.leadingAnchor.constraint(equalTo: barContent.leadingAnchor, constant: 20),
            glyph.centerYAnchor.constraint(equalTo: barContent.centerYAnchor),
            field.leadingAnchor.constraint(equalTo: glyph.trailingAnchor, constant: 12),
            field.trailingAnchor.constraint(equalTo: barContent.trailingAnchor, constant: -22),
            field.centerYAnchor.constraint(equalTo: barContent.centerYAnchor),
            scroll.topAnchor.constraint(equalTo: cardContent.topAnchor),
            scroll.leadingAnchor.constraint(equalTo: cardContent.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: cardContent.trailingAnchor),
            scroll.bottomAnchor.constraint(equalTo: footer.topAnchor, constant: -6),
            footer.leadingAnchor.constraint(equalTo: cardContent.leadingAnchor, constant: 22),
            footer.bottomAnchor.constraint(equalTo: cardContent.bottomAnchor, constant: -10),
            hints.trailingAnchor.constraint(equalTo: cardContent.trailingAnchor, constant: -22),
            hints.firstBaselineAnchor.constraint(equalTo: footer.firstBaselineAnchor),
            hints.leadingAnchor.constraint(greaterThanOrEqualTo: footer.trailingAnchor, constant: 12),
        ])
        setExpanded(false)

        // ⌘C copies the path, ⌘↩ reveals in Finder, ⌘Y toggles Quick Look
        NSEvent.addLocalMonitorForEvents(matching: .keyDown) { [weak self] e in
            guard let self, self.panel.isKeyWindow else { return e }
            if e.modifierFlags.contains(.command) {
                switch e.charactersIgnoringModifiers {
                case "c" where self.field.currentEditor()?.selectedRange.length ?? 0 == 0:
                    self.copyPath(); return nil
                case "y":
                    self.quickLook(); return nil
                case "o":
                    self.openSelected(); return nil
                default: break
                }
            }
            return e
        }
    }

    func setExpanded(_ on: Bool) {
        card.isHidden = !on
        let rows = min(hits.count, maxRows)
        let ch = 8 + CGFloat(max(rows, 1)) * rowH + 4 + 30
        cardHeight.constant = ch
        let h: CGFloat = on ? barH + gap + ch : barH
        let top = panel.frame.maxY
        var f = panel.frame
        f.size.height = h
        f.origin.y = top - h
        panel.setFrame(f, display: true)
        panel.invalidateShadow()
    }

    func toggle() {
        if panel.isVisible && panel.isKeyWindow { hide(); return }
        if let screen = NSScreen.main {
            let vf = screen.visibleFrame
            let x = vf.midX - width / 2
            let top = vf.maxY - vf.height * 0.18
            panel.setFrame(NSRect(x: x, y: top - panel.frame.height, width: width, height: panel.frame.height), display: false)
        }
        NSApp.activate(ignoringOtherApps: true)
        panel.makeKeyAndOrderFront(nil)
        field.selectText(nil)
    }

    func hide() {
        panel.orderOut(nil)
    }

    func windowDidResignKey(_ notification: Notification) {
        if QLHelper.shared.isOpen { return }
        hide()
    }

    // MARK: Search

    // While typing show fast results (tens of ms); after a 0.5 s pause ask for the reranked order
    func controlTextDidChange(_ obj: Notification) {
        pending?.cancel()
        pendingFine?.cancel()
        fineTask?.cancel()
        lastFineQuery = ""
        let q = field.stringValue
        let w = DispatchWorkItem { [weak self] in self?.run(q, fine: false) }
        pending = w
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12, execute: w)
        let f = DispatchWorkItem { [weak self] in self?.run(q, fine: true) }
        pendingFine = f
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5, execute: f)
    }

    func run(_ q: String, fine: Bool) {
        if fine { fineTask?.cancel() } else { task?.cancel() }
        if q.trimmingCharacters(in: .whitespaces).isEmpty {
            heads = []
            rebuild()
            table.reloadData()
            setExpanded(false)
            return
        }
        var c = URLComponents(string: serverURL + "/search")!
        c.queryItems = [URLQueryItem(name: "q", value: q), URLQueryItem(name: "n", value: "30"),
                        URLQueryItem(name: "rerank", value: fine ? "1" : "0")]
        let t = URLSession.shared.dataTask(with: c.url!) { [weak self] data, _, err in
            DispatchQueue.main.async {
                guard let self, self.field.stringValue == q else { return }
                if let data, let r = try? JSONDecoder().decode(SearchResponse.self, from: data) {
                    if !fine && self.lastFineQuery == q { return }  // reranked results already shown
                    if fine { self.lastFineQuery = q }
                    let keep = self.selected?.path
                    self.heads = r.results
                    self.expanded = []
                    self.rebuild()
                    let mark = (r.reranked ?? false) ? L("reranked ") : ""
                    self.footer.stringValue = r.results.isEmpty
                        ? L("Nothing found. Try describing it differently.")
                        : L("{n} results · ", ["n": r.results.count]) + "\(mark)\(r.ms) ms"
                    if fine, let keep, self.table.selectedRow > 0,
                       let i = self.hits.firstIndex(where: { $0.path == keep }) {
                        self.table.reloadData()
                        self.table.selectRowIndexes([i], byExtendingSelection: false)
                        self.setExpanded(true)
                        return
                    }
                } else if (err as? URLError)?.code == .cancelled || (fine && !self.hits.isEmpty) {
                    return  // keep the fast results if the reranked request fails
                } else {
                    self.heads = []
                    self.rebuild()
                    self.footer.stringValue = L("Cannot reach the search service ({url}); it may still be starting.", ["url": serverURL])
                }
                self.table.reloadData()
                if !self.hits.isEmpty {
                    self.table.selectRowIndexes([0], byExtendingSelection: false)
                    self.table.scrollRowToVisible(0)
                }
                self.setExpanded(true)
            }
        }
        if fine { fineTask = t } else { task = t }
        t.resume()
    }

    var lastFineQuery = ""

    func control(_ control: NSControl, textView: NSTextView, doCommandBy sel: Selector) -> Bool {
        switch sel {
        case #selector(NSResponder.moveDown(_:)): move(1); return true
        case #selector(NSResponder.moveUp(_:)): move(-1); return true
        case #selector(NSResponder.cancelOperation(_:)): hide(); return true
        case #selector(NSResponder.insertTab(_:)): toggleGroup(); return true
        case #selector(NSResponder.insertNewline(_:)):
            if NSApp.currentEvent?.modifierFlags.contains(.command) == true { revealSelected() } else { openSelected() }
            return true
        default: return false
        }
    }

    func move(_ d: Int) {
        guard !hits.isEmpty else { return }
        let r = max(0, min(hits.count - 1, table.selectedRow + d))
        table.selectRowIndexes([r], byExtendingSelection: false)
        table.scrollRowToVisible(r)
        if QLHelper.shared.isOpen { QLHelper.shared.show(URL(fileURLWithPath: hits[r].path)) }
    }

    var selected: Hit? {
        let r = table.selectedRow
        return r >= 0 && r < hits.count ? hits[r] : nil
    }

    // Tell the service which file was opened for this query (stored locally), so files you
    // open often move up
    func logOpen(_ path: String) {
        var r = URLRequest(url: URL(string: serverURL + "/opened")!)
        r.httpMethod = "POST"
        r.setValue("1", forHTTPHeaderField: "X-SemSearch")
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
        r.httpBody = try? JSONSerialization.data(withJSONObject: ["path": path, "query": field.stringValue])
        URLSession.shared.dataTask(with: r).resume()
    }

    @objc func openSelected() {
        guard let h = selected else { return }
        logOpen(h.path)
        hide()
        NSWorkspace.shared.open(URL(fileURLWithPath: h.path))
    }

    func revealSelected() {
        guard let h = selected else { return }
        logOpen(h.path)
        hide()
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: h.path)])
    }

    func copyPath() {
        guard let h = selected else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(h.path, forType: .string)
        footer.stringValue = L("Copied: ") + h.path
    }

    func quickLook() {
        guard let h = selected else { return }
        QLHelper.shared.toggle(URL(fileURLWithPath: h.path))
    }

    // MARK: Table

    func numberOfRows(in tableView: NSTableView) -> Int { hits.count }

    func tableView(_ tableView: NSTableView, viewFor tableColumn: NSTableColumn?, row: Int) -> NSView? {
        let id = NSUserInterfaceItemIdentifier("cell")
        let cell = (tableView.makeView(withIdentifier: id, owner: nil) as? ResultCell) ?? {
            let c = ResultCell(frame: .zero)
            c.identifier = id
            return c
        }()
        cell.show(hits[row], child: childPaths.contains(hits[row].path), expanded: expanded.contains(hits[row].path))
        return cell
    }

    func tableView(_ tableView: NSTableView, rowViewForRow row: Int) -> NSTableRowView? { RowView() }
}

// MARK: - Quick Look


final class QLHelper: NSObject, QLPreviewPanelDataSource {
    static let shared = QLHelper()
    var url: URL?
    var isOpen: Bool { QLPreviewPanel.sharedPreviewPanelExists() && QLPreviewPanel.shared().isVisible }

    func toggle(_ u: URL) {
        if isOpen { QLPreviewPanel.shared().orderOut(nil); return }
        show(u)
    }

    func show(_ u: URL) {
        url = u
        let p = QLPreviewPanel.shared()!
        p.dataSource = self
        p.reloadData()
        p.makeKeyAndOrderFront(nil)
    }

    func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int { url == nil ? 0 : 1 }
    func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! { url as NSURL? }
}

// MARK: - App

final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    var status: NSStatusItem!
    var controller: SearchController!
    var hotkey: HotKey!
    let statusLine = NSMenuItem(title: L("Loading index status…"), action: nil, keyEquivalent: "")

    var server: Process?
    var quitting = false
    var misses = 0
    let repo = repoDir

    // The app launches the service so macOS folder access is granted once, to this app
    func startServer() {
        if quitting { return }
        var req = URLRequest(url: URL(string: serverURL + "/status")!)
        req.timeoutInterval = 8
        URLSession.shared.dataTask(with: req) { [weak self] _, resp, _ in
            guard let self else { return }
            if resp != nil {  // a service is already running (503 while starting counts)
                self.misses = 0
                DispatchQueue.main.asyncAfter(deadline: .now() + 60) { self.startServer() }
                return
            }
            DispatchQueue.main.async {
                // our own child is alive: leave it; otherwise restart after two misses in a row
                if let p = self.server, p.isRunning {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 30) { self.startServer() }
                    return
                }
                self.misses += 1
                if self.misses >= 2 || self.server == nil {
                    self.misses = 0
                    self.spawnServer()
                } else {
                    DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self.startServer() }
                }
            }
        }.resume()
    }

    func spawnServer() {
        let p = Process()
        p.executableURL = URL(fileURLWithPath: repo + "/.venv/bin/python")
        p.arguments = ["-m", "semsearch.server"]
        p.currentDirectoryURL = URL(fileURLWithPath: repo)
        let logDir = NSHomeDirectory() + "/.semsearch"
        try? FileManager.default.createDirectory(atPath: logDir, withIntermediateDirectories: true)
        let logPath = logDir + "/server.log"
        if !FileManager.default.fileExists(atPath: logPath) {
            FileManager.default.createFile(atPath: logPath, contents: nil)
        }
        if let fh = FileHandle(forWritingAtPath: logPath) {
            fh.seekToEndOfFile()
            p.standardOutput = fh
            p.standardError = fh
        }
        p.terminationHandler = { [weak self] _ in
            DispatchQueue.main.asyncAfter(deadline: .now() + 5) { self?.startServer() }
        }
        do {
            try p.run()
            server = p
        } catch {
            DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in self?.startServer() }
        }
    }

    func applicationWillTerminate(_ n: Notification) {
        quitting = true
        server?.terminate()
    }

    var sigterm: DispatchSourceSignal?

    func applicationDidFinishLaunching(_ n: Notification) {
        // On kill / launchctl stop, shut the service down too
        signal(SIGTERM, SIG_IGN)
        sigterm = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        sigterm?.setEventHandler { NSApp.terminate(nil) }
        sigterm?.resume()
        if let i = CommandLine.arguments.firstIndex(of: "--snapshot"), i + 1 < CommandLine.arguments.count {
            snapshot(to: CommandLine.arguments[i + 1])
            return
        }
        startServer()
        controller = SearchController()
        hotkey = HotKey(keyCode: UInt32(kVK_Space), modifiers: UInt32(optionKey)) { [weak self] in
            self?.controller.toggle()
        }
        status = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        status.button?.image = NSImage(systemSymbolName: "sparkle.magnifyingglass", accessibilityDescription: "SemSearch")
        let menu = NSMenu()
        menu.delegate = self
        let open = NSMenuItem(title: L("Search"), action: #selector(openSearch), keyEquivalent: " ")
        open.keyEquivalentModifierMask = [.option]
        menu.addItem(open)
        menu.addItem(.separator())
        menu.addItem(statusLine)
        menu.addItem(NSMenuItem(title: L("Update Index Now"), action: #selector(reindex), keyEquivalent: ""))
        menu.addItem(NSMenuItem(title: L("Open Web Version"), action: #selector(openWeb), keyEquivalent: ""))
        menu.addItem(.separator())
        menu.addItem(NSMenuItem(title: L("Quit SemSearch"), action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q"))
        for i in menu.items where i.action != nil && i.action != #selector(NSApplication.terminate(_:)) { i.target = self }
        status.menu = menu
        if CommandLine.arguments.contains("--show") {
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { self.controller.toggle() }
        }
        if let i = CommandLine.arguments.firstIndex(of: "--query"), i + 1 < CommandLine.arguments.count {
            let q = CommandLine.arguments[i + 1]
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.8) {
                self.controller.field.stringValue = q
                self.controller.controlTextDidChange(Notification(name: NSControl.textDidChangeNotification))
            }
        }
    }

    // For screenshots/tests: render the panel over a gradient to a PNG and quit, without showing it.
    // System glass is only composited on screen, so translucent fills stand in for it here.
    func snapshot(to out: String) {
        if CommandLine.arguments.contains("--dark") { NSApp.appearance = NSAppearance(named: .darkAqua) }
        controller = SearchController()
        let q = CommandLine.arguments.firstIndex(of: "--query").map { CommandLine.arguments[$0 + 1] } ?? ""
        controller.field.stringValue = q
        controller.run(q, fine: true)
        // Order it in far off-screen (invisible, no focus change) so the views actually draw
        controller.panel.setFrameOrigin(NSPoint(x: -20000, y: -20000))
        controller.panel.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline: .now() + 4) {
            let v = self.controller.panel.contentView!
            v.layoutSubtreeIfNeeded()
            let pad: CGFloat = 40
            let size = NSSize(width: v.bounds.width + pad * 2, height: v.bounds.height + pad * 2)
            guard let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(size.width * 2), pixelsHigh: Int(size.height * 2),
                                             bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                             colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { NSApp.terminate(nil); return }
            rep.size = size
            NSGraphicsContext.saveGraphicsState()
            NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
            NSApp.effectiveAppearance.performAsCurrentDrawingAppearance {
                let dark = CommandLine.arguments.contains("--dark")
                NSGradient(starting: dark ? NSColor(red: 0.10, green: 0.14, blue: 0.28, alpha: 1) : NSColor(red: 0.62, green: 0.75, blue: 0.93, alpha: 1),
                           ending: dark ? NSColor(red: 0.28, green: 0.12, blue: 0.30, alpha: 1) : NSColor(red: 0.93, green: 0.80, blue: 0.86, alpha: 1))!
                    .draw(in: NSRect(origin: .zero, size: size), angle: -60)
                for part in self.controller.glassParts where !part.outer.isHidden {
                    let f = part.outer.convert(part.outer.bounds, to: v)
                    let r = NSRect(x: pad + f.minX, y: pad + (v.isFlipped ? v.bounds.height - f.maxY : f.minY),
                                   width: f.width, height: f.height)
                    let radius = f.height <= 60 ? f.height / 2 : 24
                    (dark ? NSColor(white: 0.12, alpha: 0.72) : NSColor(white: 1, alpha: 0.62)).setFill()
                    NSBezierPath(roundedRect: r, xRadius: radius, yRadius: radius).fill()
                    let c = part.content
                    let cf = c.convert(c.bounds, to: v)
                    let cr = NSRect(x: pad + cf.minX, y: pad + (v.isFlipped ? v.bounds.height - cf.maxY : cf.minY),
                                    width: cf.width, height: cf.height)
                    if let cRep = c.bitmapImageRepForCachingDisplay(in: c.bounds) {
                        c.cacheDisplay(in: c.bounds, to: cRep)
                        cRep.draw(in: cr, from: .zero, operation: .sourceOver, fraction: 1, respectFlipped: true, hints: nil)
                    }
                }
            }
            NSGraphicsContext.restoreGraphicsState()
            try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: out))
            NSApp.terminate(nil)
        }
    }

    func menuWillOpen(_ menu: NSMenu) {
        URLSession.shared.dataTask(with: URL(string: serverURL + "/status")!) { [weak self] data, _, _ in
            var text = L("Search service not responding")
            if let data, let j = try? JSONSerialization.jsonObject(with: data) as? [String: Any] {
                let files = j["files"] as? Int ?? 0
                let last = j["last_index"] as? String ?? L("not yet")
                let busy = (j["indexing"] as? Bool ?? false) ? L(", updating") : ""
                text = L("{files} items indexed · last update {last}{busy}", ["files": files, "last": last, "busy": busy])
                if let blocked = j["no_access"] as? [String], !blocked.isEmpty {
                    let names = blocked.map { ($0 as NSString).lastPathComponent }.joined(separator: L(", "))
                    text = L("⚠︎ Needs access: {names}. Allow SemSearch in System Settings > Privacy & Security > Files and Folders", ["names": names])
                }
            }
            DispatchQueue.main.async { self?.statusLine.title = text }
        }.resume()
    }

    @objc func openSearch() { controller.toggle() }
    @objc func openWeb() { NSWorkspace.shared.open(URL(string: serverURL)!) }
    @objc func reindex() {
        var r = URLRequest(url: URL(string: serverURL + "/reindex")!)
        r.httpMethod = "POST"
        r.setValue("1", forHTTPHeaderField: "X-SemSearch")
        URLSession.shared.dataTask(with: r).resume()
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
