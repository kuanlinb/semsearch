// semsearch-fswatch: watch folders with macOS FSEvents and print one line (a path) per change.
// Usage: semsearch-fswatch <dir>...   (exits on its own when the parent process goes away)
// A separate helper because Python's watchdog can hold the GIL in native code and freeze
// the search service.
import CoreServices
import Foundation

let paths = Array(CommandLine.arguments.dropFirst())
if paths.isEmpty {
    FileHandle.standardError.write("usage: semsearch-fswatch <dir>...\n".data(using: .utf8)!)
    exit(2)
}
setvbuf(stdout, nil, _IOLBF, 0)

let callback: FSEventStreamCallback = { _, _, count, eventPaths, _, _ in
    let list = unsafeBitCast(eventPaths, to: NSArray.self) as? [String] ?? []
    for i in 0..<min(count, list.count) {
        let name = (list[i] as NSString).lastPathComponent
        if name.hasPrefix(".") || name.hasSuffix(".download") || name.hasSuffix(".crdownload")
            || name.hasSuffix(".part") || name.hasSuffix(".tmp") {
            continue  // hidden files and downloads still in progress don't count
        }
        print(list[i])
    }
}

let flags = UInt32(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagNoDefer | kFSEventStreamCreateFlagUseCFTypes)
guard let stream = FSEventStreamCreate(nil, callback, nil, paths as CFArray,
                                       FSEventStreamEventId(kFSEventStreamEventIdSinceNow), 2.0, flags) else {
    exit(1)
}
FSEventStreamSetDispatchQueue(stream, DispatchQueue.global(qos: .background))
FSEventStreamStart(stream)

// Exit when the parent (the search service) is gone, so no orphan is left behind
let parent = getppid()
Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { _ in
    if getppid() != parent { exit(0) }
}
RunLoop.main.run()
