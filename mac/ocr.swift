// semsearch-ocr: recognize text in images and scanned PDFs with the built-in macOS Vision framework.
// Reads one path per line on stdin and prints one JSON line per file: {"path": ..., "text": ...}
// A fast "is there any text?" pass runs first, so photos without text skip full recognition.
import AppKit
import Foundation
import PDFKit
import Vision

let maxSide: CGFloat = 2200      // larger images are downscaled first (faster, same accuracy)
let maxPdfPages = 5              // only the first pages of a scanned PDF
let minTextBoxes = 1             // run full recognition when at least one line of text is detected

func cgImage(_ url: URL) -> CGImage? {
    guard let src = CGImageSourceCreateWithURL(url as CFURL, nil) else { return nil }
    let opts: [CFString: Any] = [
        kCGImageSourceCreateThumbnailFromImageAlways: true,
        kCGImageSourceThumbnailMaxPixelSize: maxSide,
        kCGImageSourceCreateThumbnailWithTransform: true,
    ]
    return CGImageSourceCreateThumbnailAtIndex(src, 0, opts as CFDictionary)
}

func pdfPages(_ url: URL) -> [CGImage] {
    guard let doc = PDFDocument(url: url) else { return [] }
    var out: [CGImage] = []
    for i in 0..<min(doc.pageCount, maxPdfPages) {
        guard let page = doc.page(at: i) else { continue }
        let box = page.bounds(for: .mediaBox)
        let scale = min(2.0, maxSide / max(box.width, box.height, 1))
        let img = page.thumbnail(of: CGSize(width: box.width * scale, height: box.height * scale), for: .mediaBox)
        if let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) { out.append(cg) }
    }
    return out
}

func hasText(_ img: CGImage) -> Bool {
    let req = VNDetectTextRectanglesRequest()
    try? VNImageRequestHandler(cgImage: img).perform([req])
    return (req.results?.count ?? 0) >= minTextBoxes
}

func recognize(_ img: CGImage) -> String {
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["zh-Hant", "zh-Hans", "en-US", "ja-JP"]
    req.usesLanguageCorrection = true
    try? VNImageRequestHandler(cgImage: img).perform([req])
    return (req.results ?? []).compactMap { $0.topCandidates(1).first?.string }.joined(separator: "\n")
}

func ocr(_ path: String) -> String {
    let url = URL(fileURLWithPath: path)
    let images = url.pathExtension.lowercased() == "pdf" ? pdfPages(url) : [cgImage(url)].compactMap { $0 }
    return images.filter(hasText).map(recognize).joined(separator: "\n")
}

while let line = readLine() {
    let path = line.trimmingCharacters(in: .whitespacesAndNewlines)
    if path.isEmpty { continue }
    let text = autoreleasepool { ocr(path) }
    let obj: [String: String] = ["path": path, "text": text]
    if let data = try? JSONSerialization.data(withJSONObject: obj),
       let s = String(data: data, encoding: .utf8) {
        print(s)
        fflush(stdout)
    }
}
