# SemSearch

[English](README.md) · **繁體中文**

**用一句話描述，就能在 Mac 上找到檔案和 App，什麼語言都可以。**

Spotlight 要記得檔名裡的字才找得到。SemSearch 看得懂意思，就算完全不記得檔案叫什麼也找得到。全部在你的 Mac 上執行，檔案和搜尋內容都不會上傳。

*🔊 影片預設靜音，請點播放器上的喇叭圖示打開聲音。*

https://github.com/user-attachments/assets/2354e0be-d25c-4235-b245-920a87ae6892

## 它能做什麼

| 你打的字 | 它找到的 | Spotlight 為什麼找不到 |
|---|---|---|
| 房租多少 | 存成 `Document (3).txt` 的租約 | 檔名和內文都沒有「房租」 |
| 車險什麼時候要續約 | `scan_0042.pdf`（一份 motor vehicle policy） | 它比對的是意思，不是字 |
| beef noodle soup recipe | `紅燒牛肉麵.md` | 英文問、中文檔 |
| 寫筆記的 app | 備忘錄、Goodnotes、OneNote | 它知道每個 App 是做什麼的 |
| 垃圾桶 | 垃圾桶 | 常用位置也找得到 |

| 英文問題找到叫 `Document (3).txt` 的租約 | 中文問題找到英文 PDF（中文介面） |
|---|---|
| ![“how much is my rent” 找到 Document (3).txt](docs/screenshot-en.png) | ![「車險什麼時候要續約」找到 scan_0042.pdf](docs/screenshot-zh.png) |

*（影片和截圖用的都是 [`demo/`](demo) 資料夾裡的虛構範例檔案。）*

## 安裝

**需要**：M1 以後的 Mac（Apple 晶片）、macOS 13 以上、約 4 GB 空間。

**1. 安裝 Apple 開發者工具**（只要一次，已經裝過 Xcode 可跳過）：

```bash
xcode-select --install
```

**2. 下載並安裝 SemSearch：**

```bash
git clone https://github.com/kuanlinb/semsearch.git
cd semsearch
./install.sh
```

**3. macOS 詢問能不能讀取「文件」「桌面」「下載項目」時，按「允許」。**

這樣就好了。之後每次登入會自動啟動。接下來會發生的事：

- 第一次會下載語言模型（約 2.3 GB，只下載一次）。
- **幾分鐘內就能用檔名搜尋**，16 萬個檔案大約 15 分鐘。 讀完所有文件的內文要比較久，資料少的話幾分鐘，16 萬個檔案大約 2 小時，期間可以照常搜尋。
- `semsearch` 資料夾請不要移動或刪除，App 會從那裡執行。

> 如果安裝程式說 Python 版本太舊，執行 `brew install python`（或安裝 [uv](https://github.com/astral-sh/uv)）後，再跑一次 `./install.sh`。

## 怎麼用

按 **⌥ Space**（Option＋空白鍵），用自己的話描述要找的東西，按 **↩** 開啟。

| 按鍵 | 功能 |
|---|---|
| ↩ | 開啟檔案或 App |
| ⌘ ↩ | 在 Finder 顯示 |
| ⌘ Y | 快速查看 |
| ⌘ C | 複製路徑 |
| Tab | 展開同資料夾的其他結果 |
| Esc | 關閉 |

**小技巧**

- 像跟朋友說話一樣描述：「上課講 attention 的投影片」「新筆電的收據」。
- 加上類型字可以縮小範圍：「…pdf」「…簡報」「…資料夾」「…app」。
- 用中文問、檔案是英文也找得到，反過來也可以。
- 按 ⌥ Space 沒反應？通常是別的 App 佔用了這個快捷鍵，可以[換一個快捷鍵](docs/troubleshooting.md#space-does-nothing)。
- 也可以從選單列的放大鏡圖示、瀏覽器 `http://127.0.0.1:8799`，或終端機 `ss 你的問題` 來搜尋。
- 介面語言跟著系統：支援英文、繁體中文、簡體中文、日文、韓文，其他語言顯示英文。

## 特色

- **會讀內文**：PDF、Word、PowerPoint、Excel、Markdown、純文字、Jupyter 筆記本，連截圖和掃描版 PDF 裡的字也讀得到。
- **用途找 App**：打「截圖」會找到截圖 App，打「開視訊會議」會找到 FaceTime。
- **什麼語言都可以**：中文問找到英文檔，英文問找到中文檔。
- **介面支援五種語言**：英文、繁體中文、簡體中文、日文、韓文，跟著系統切換。歡迎[幫忙翻譯其他語言](l10n/README.md)。
- **越用越準**：常打開的檔案會往前排，紀錄只存在你的 Mac。
- **新檔案很快就搜得到**：下載的新檔案約 30 秒後就找得到。
- **雲端硬碟**：iCloud、OneDrive、Google Drive、Dropbox 裡只在雲端的檔案，只用檔名找，不會下載。
- **隱私**：全部在你的 Mac 上執行。也可以選擇用你另一台有顯示卡的電腦幫忙[重新排序](remote/README.md)，讓結果更準。

## 進一步了解

以下文件目前是英文：

- [設定](docs/configuration.md)：加入資料夾、排除路徑、關閉文字辨識、更改連接埠
- [運作方式](docs/how-it-works.md)：架構圖、搜尋流程、模型怎麼選的
- [限制、移除與開發](docs/troubleshooting.md)

## 授權

MIT，見 [LICENSE](LICENSE)。
