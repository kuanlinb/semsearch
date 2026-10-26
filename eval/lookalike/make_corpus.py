"""Build the distractor corpus: ~300 fictional personal files with near-duplicates on purpose.

    .venv/bin/python eval/lookalike/make_corpus.py <out_dir>

Seeded, so the same files come out every time. Everything is made up. Each topic has look-alikes
(three leases, three motor-type policies, many monthly bills, several flights, two beef noodle
recipes…) so a search has to find the right one, not just the right topic. Formats: txt, md, docx,
xlsx, pptx, text PDFs (cupsfilter), scanned PDFs (image only) and phone/desktop screenshots (PNG),
the last two readable only through OCR.
"""
import os
import random
import shutil
import subprocess
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

R = random.Random(20261026)
OUT = ""
FONT = "/System/Library/Fonts/Hiragino Sans GB.ttc"


def path(rel):
    p = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    return p


def txt(rel, text):
    open(path(rel), "w").write(text.strip() + "\n")


def pdf(rel, text):
    """A PDF with a text layer, the way a printed-to-PDF document has one."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as f:
        f.write(text.strip() + "\n")
    with open(path(rel), "wb") as out:
        subprocess.run(["/usr/sbin/cupsfilter", f.name], stdout=out, stderr=subprocess.DEVNULL, check=True)
    os.unlink(f.name)


def _render(text, width, size, pad=60, bg="white", fg="black"):
    font = ImageFont.truetype(FONT, size)
    lines = text.strip().split("\n")
    height = pad * 2 + int(len(lines) * size * 1.6)
    img = Image.new("RGB", (width, max(height, 400)), bg)
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((pad, pad + i * size * 1.6), line, font=font, fill=fg)
    return img


def screenshot(rel, text, phone=True):
    img = _render(text, 1179 if phone else 1600, 44 if phone else 30, pad=80 if phone else 50)
    img.save(path(rel))


def scan(rel, text):
    """An image-only PDF: a slightly grey, slightly tilted page with no text layer."""
    img = _render(text, 1700, 34, pad=120, bg=(236, 234, 228), fg=(40, 40, 40))
    img = img.rotate(R.uniform(-1.2, 1.2), expand=True, fillcolor=(236, 234, 228)).filter(ImageFilter.GaussianBlur(0.6))
    img.save(path(rel), "PDF", resolution=150)


def docx(rel, title, paras):
    import docx as d
    doc = d.Document()
    doc.add_heading(title, 1)
    for p in paras:
        doc.add_paragraph(p)
    doc.save(path(rel))


def xlsx(rel, sheet, rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet
    for r in rows:
        ws.append(r)
    wb.save(path(rel))


def pptx(rel, slides):
    from pptx import Presentation
    p = Presentation()
    for title, body in slides:
        s = p.slides.add_slide(p.slide_layouts[1])
        s.shapes.title.text = title
        s.placeholders[1].text = body
    p.save(path(rel))


# ---------------------------------------------------------------- Home
def home():
    txt("Home/Document (3).txt", """
Residential tenancy agreement for the apartment.
The tenant pays the landlord NT$15,000 each month, before the 5th. Security deposit: two months.
Term: 1 July 2025 to 30 June 2027. Repairs must be reported to the landlord in writing.""")
    txt("Home/Document (5).txt", """
Tenancy agreement, Lane 88, Songren Road, Xinyi District (previous flat).
Monthly rent NT$12,500, due on the 10th. Deposit: one and a half months.
Term: 1 August 2022 to 31 July 2024. The tenant may not keep pets. Ended; deposit returned 6 August 2024.""")
    docx("Home/車位租約.docx", "停車位租賃契約", [
        "出租標的：地下二樓 B2-17 平面車位一格。",
        "租金每月新台幣 2,800 元，每月 1 日前匯款至出租人帳戶。押金一個月。",
        "租期自 2025 年 9 月 1 日起至 2026 年 8 月 31 日止。遙控器一支，遺失需賠償 1,500 元。"])
    pdf("Home/Lease_storage_unit.pdf", """
Self-storage rental agreement
Unit 3F-C08, 2.1 m x 1.5 m, climate controlled.
Monthly fee NT$1,900, charged to card on the 15th. Minimum term six months from 15 January 2026.
Access hours 06:00-23:00 with the member card.""")
    txt("Home/冷氣保固卡.txt", """
冷氣保固卡
機型：變頻分離式冷氣 5.0 kW。安裝日期：2025 年 6 月 18 日。
保固：主機 7 年、壓縮機 10 年。報修請準備機身序號與安裝發票。""")
    pdf("Home/冰箱保固書.pdf", """
冰箱保固書
雙門變頻冰箱 485 公升，購買日期 2024 年 11 月 3 日。
整機保固 3 年，壓縮機保固 5 年。保固期間到府維修免收工資。""")
    txt("Home/washing_machine_warranty.txt", """
Washing machine warranty card
Front-loading washer 11 kg, purchased 2 March 2025.
Whole unit covered for 2 years; the direct-drive motor for 10 years. Keep the receipt.""")
    txt("Home/除濕機使用說明.md", """
# 除濕機使用說明
水箱滿了會自動停機並亮紅燈。濾網每兩週清洗一次。
連續除濕模式要接排水管。冬天室溫低於 5 度時效率會下降。""")
    scan("Home/Scan_20260211.pdf", """
房屋稅繳款書
課稅所屬期間：115 年
應納稅額：新臺幣 4,382 元
繳納期間：115 年 5 月 1 日至 5 月 31 日
逾期每 3 日加徵 1% 滯納金""")
    screenshot("Home/IMG_4471.png", """
社區公告
停水通知
3 月 18 日（三）09:00–17:00
水塔清洗，全棟停水
請住戶提前儲水
管理委員會""")
    for i, (month, fee) in enumerate([("1", 2150), ("2", 2150), ("3", 2380), ("4", 2380)]):
        screenshot(f"Home/管理費/Screenshot 2026-0{month}-0{i + 3} at 09.1{i}.22.png", f"""
管理費繳費成功
2026 年 {month} 月份管理費
金額 NT$ {fee:,}
戶號 12F-3
繳費時間 2026/0{month}/0{i + 3} 09:1{i}""", phone=False)
    txt("Home/搬家清單.md", """
# 搬家清單
- 打包書櫃、廚房用品
- 網路移機（提前兩週申請）
- 更新戶籍地址、銀行地址
- 舊屋押金退還確認""")
    txt("Home/plant_care.md", """
# Plant care
Monstera: water when the top 3 cm of soil is dry. Pothos: every 7-10 days. Snake plant: every 3 weeks.
Repot the monstera in spring.""")


# ---------------------------------------------------------------- Finance
def finance():
    pdf("Finance/scan_0042.pdf", """
Motor vehicle policy: renewal notice
Your automobile coverage runs from 1 May 2026 to 30 April 2027:
third-party liability, collision and roadside assistance.
Annual premium NT$18,600, payable before 25 April 2026 to keep the no-claims discount.""")
    pdf("Finance/scan_0017.pdf", """
Motor vehicle policy schedule
Period of cover: 1 May 2025 to 30 April 2026. Third-party liability and collision.
Annual premium NT$19,900. Excess NT$3,000 per claim. This policy has expired.""")
    pdf("Finance/機車強制險.pdf", """
機車強制汽車責任保險 保險證
保險期間：2026 年 2 月 10 日至 2028 年 2 月 10 日（兩年期）
保險費：新台幣 1,250 元
車牌號碼：MXV-2291""")
    docx("Finance/health_insurance_summary.docx", "Health insurance summary", [
        "Hospital cash benefit NT$2,000 per day, up to 365 days.",
        "Medical expense reimbursement up to NT$150,000 per stay. Surgery benefit by schedule.",
        "Premium NT$24,360 a year, paid annually each 20 October."])
    txt("Finance/火險保單.txt", """
住宅火災及地震基本保險
保險標的：自住公寓，建築物保額 150 萬元。
保險費：每年新台幣 1,480 元，2026 年 1 月 5 日續保。""")
    pdf("Finance/旅平險.pdf", """
旅行平安保險 投保證明
旅遊地點：日本　保障期間：2026/04/02–2026/04/07
意外身故保額 新台幣 500 萬元，海外突發疾病醫療 50 萬元，旅遊不便險含班機延誤。
保費 NT$ 612""")
    # Utility bills: 18 months, look-alikes on purpose
    for y, m in [(2025, m) for m in range(1, 13)] + [(2026, m) for m in range(1, 7)]:
        if (y, m) == (2026, 3):
            txt(f"Finance/Bills/{y}/2026-03 水電費繳費單.txt", """
2026 年 3 月水電費繳費單
電費 1,286 元（計費期間 2/5–4/4），自來水 432 元，合計 1,718 元，繳費期限 4 月 15 日。
可用超商或網路銀行繳費。""")
            continue
        e = R.randrange(900, 3200) if m in (6, 7, 8, 9) else R.randrange(700, 1500)
        w = R.randrange(300, 520)
        txt(f"Finance/Bills/{y}/{y}-{m:02d} 水電費繳費單.txt", f"""
{y} 年 {m} 月水電費繳費單
電費 {e:,} 元，自來水 {w} 元，合計 {e + w:,} 元，繳費期限 {m % 12 + 1} 月 15 日。
可用超商或網路銀行繳費。""")
    for m in range(1, 13):
        amt = R.choice([599, 599, 699, 699, 899]) + R.randrange(0, 120)
        txt(f"Finance/Bills/telecom/電信帳單_2025{m:02d}.txt", f"""
行動電話帳單 2025 年 {m} 月
月租費 {amt - 30} 元，加值服務 30 元，本期應繳 {amt} 元。帳號 8812-0045-37。""")
    for m in range(1, 9):
        amt = R.randrange(8000, 42000)
        pdf(f"Finance/Statements/Statement_2026-{m:02d}.pdf", f"""
Credit card statement, {['January','February','March','April','May','June','July','August'][m - 1]} 2026
Card ending 4417. New balance NT${amt:,}. Minimum payment NT${amt // 10:,}.
Payment due on the 22nd. Largest item: {R.choice(['online shopping','supermarket','restaurant','airline','electronics store'])}.""")
    xlsx("Finance/2025 報稅整理.xlsx", "綜所稅", [
        ["項目", "金額"], ["薪資所得", 1182000], ["利息所得", 3410], ["列舉扣除：保險費", 24000],
        ["應退稅額", 7630], ["退稅入帳日", "2025-08-29"]])
    screenshot("Finance/IMG_5203.png", """
COSTCO 好市多 新莊店
2026/05/17 14:32
科克蘭衛生紙 x1   559
冷凍水餃 x2       638
有機雞蛋 x1       289
……
合計 NT$ 3,486
信用卡 ****4417""")
    screenshot("Finance/IMG_5310.png", """
轉帳成功
轉入帳號 (822) ****5521
金額 NT$ 15,000
備註 2026年6月房租
2026/06/03 08:12""")
    txt("Finance/budget_2026.md", """
# Budget 2026
Rent 15,000 · Food 12,000 · Transport 2,500 · Insurance (monthly share) 4,200 · Savings 20,000.
Goal: emergency fund of six months by December.""")
    txt("Finance/投資筆記.md", """
# 投資筆記
定期定額每月 5 號扣款 10,000 元，標的為全市場 ETF。
不追高、不看盤，一年檢查一次資產配置。""")


# ---------------------------------------------------------------- Travel
def travel():
    txt("Travel/flight_confirmation.txt",
        "Booking confirmation: TPE → KIX, 2026-04-02 08:35, seat 32A. Return KIX → TPE 2026-04-07 18:10.")
    txt("Travel/flight_confirmation (1).txt", """
Booking confirmation Q7XK2P: TPE → NRT, 2025-11-14 14:20, seat 41C.
Return NRT → TPE 2025-11-19 20:45. Checked baggage 23 kg.""")
    pdf("Travel/eticket_SIN.pdf", """
Electronic ticket receipt
Booking reference ZT4M9L
Taipei (TPE) to Singapore (SIN), 21 August 2026, departs 07:50, arrives 12:15.
Singapore (SIN) to Taipei (TPE), 26 August 2026, departs 13:30.""")
    screenshot("Travel/IMG_6012.png", """
登機證 BOARDING PASS
高雄 KHH → 香港 HKG
航班 BR 2196
日期 2026/01/23
登機時間 10:05
座位 12F
登機門 B4""")
    screenshot("Travel/IMG_6020.png", """
台灣高鐵 電子車票
台北 → 左營
2026/02/14
08:01 開 → 09:35 到
7 車 9A
票價 NT$ 1,490""")
    txt("Travel/Kansai_2026.md", """
# Kansai itinerary: five days in Kyoto and Nara
Day 1 Kansai airport to Kyoto Station, hotel near Shijo-Karasuma. Day 2 Fushimi Inari, Kiyomizu-dera.
Day 3 Arashiyama bamboo grove. Day 4 Nara Park and the deer. Day 5 Nishiki Market, then the HARUKA back to the airport.""")
    txt("Travel/Tokyo_2025.md", """
# Tokyo, four days
Day 1 Asakusa and Senso-ji, hotel in Ueno. Day 2 teamLab and Odaiba. Day 3 Shimokitazawa vintage shops.
Day 4 Tsukiji outer market, then the Skyliner to Narita.""")
    txt("Travel/新加坡筆記.md", """
# 新加坡筆記
濱海灣花園晚上 7:45 有燈光秀。牛車水吃海南雞飯。
地鐵用信用卡感應就能搭，不用買卡。8 月很熱，記得帶傘。""")
    pdf("Travel/Hotel_Kyoto_booking.pdf", """
Reservation confirmed. Confirmation number 58210377.
Hotel near Shijo-Karasuma, Kyoto. Check-in 2 April 2026, check-out 6 April 2026, 4 nights.
Twin room, breakfast included. Free cancellation until 30 March.""")
    pdf("Travel/Hotel_Tokyo_booking.pdf", """
Reservation confirmed. Confirmation number 44718250.
Hotel in Ueno, Tokyo. Check-in 14 November 2025, check-out 19 November 2025, 5 nights.
Double room, no breakfast.""")
    txt("Travel/護照換發.md", """
# 護照換發
現在的護照效期到 2027 年 3 月。出國前要剩六個月以上效期，2026 年底前去外交部領務局換發。
需要：兩吋照片兩張、身分證、舊護照。""")
    txt("Travel/packing_list.md", """
# Packing list
Passport, adapter (Japan uses type A, same as Taiwan), IC card, umbrella, power bank, medicine.""")


# ---------------------------------------------------------------- Recipes
RECIPES = {
    "紅燒牛肉麵.md": """
# 紅燒牛肉麵（4 人份）
材料：牛腱 600 g、牛肋條 300 g、番茄 2 顆、洋蔥 1 顆、豆瓣醬 2 大匙、醬油 4 大匙、八角 2 顆、冰糖 1 小匙。
步驟：牛肉切塊汆燙；炒香豆瓣醬與洋蔥，加入番茄和牛肉翻炒；加水淹過，小火燉 90 分鐘。
麵條另外煮，起鍋前加青江菜與蔥花。""",
    "清燉牛肉麵.md": """
# 清燉牛肉麵
材料：牛腱 800 g、白蘿蔔半條、薑片、米酒、鹽、白胡椒。
牛肉汆燙後與蘿蔔、薑加水，小火燉 2 小時，只用鹽調味，湯頭清澈。""",
    "番茄牛腩.md": """
# 番茄牛腩
牛腩 600 g 切塊，番茄 4 顆，洋蔥 1 顆，番茄醬 2 大匙。燉 70 分鐘，最後收汁，配白飯。""",
    "beef_stew.md": """
# Red wine beef stew
1 kg chuck, 500 ml red wine, carrots, celery, thyme. Brown the beef, deglaze with the wine,
simmer covered in the oven at 160 °C for 2.5 hours.""",
    "sourdough_starter.md": """
# Sourdough starter, day by day
Day 1: 50 g whole-wheat flour + 50 g water, cover loosely. Day 2–6: discard half, feed 50 g flour + 50 g water.
Ready when it doubles within 6 hours of feeding and smells mildly sour. Keep in the fridge, feed weekly.""",
    "sourdough_loaf.md": """
# Sourdough loaf
100 g active starter, 375 g water, 500 g bread flour, 10 g salt. Stretch and fold every 30 min for 2 h,
bulk ferment 4-6 h, shape, cold proof overnight. Bake at 250 °C in a Dutch oven, 20 min lid on, 25 off.""",
    "麻婆豆腐.md": """
# 麻婆豆腐
嫩豆腐一盒、豬絞肉 150 g、豆瓣醬 1 大匙、花椒粉、蒜末、太白粉水。豆腐切丁先燙過，炒香絞肉和豆瓣醬後下豆腐，勾芡。""",
    "滷肉飯.md": """
# 滷肉飯
豬五花 600 g 切小條，紅蔥頭酥、醬油、冰糖、五香粉。小火滷 1 小時，最後加滷蛋。""",
    "三杯雞.md": """
# 三杯雞
雞腿 2 隻，麻油、米酒、醬油各一杯（其實各 3 大匙就夠），薑片、蒜頭、九層塔。砂鍋收汁。""",
    "pancakes.md": """
# Fluffy pancakes
200 g flour, 2 tsp baking powder, 1 egg, 250 ml milk, 30 g melted butter. Rest the batter 10 min.""",
    "banana_bread.md": """
# Banana bread
3 overripe bananas, 250 g flour, 1 tsp baking soda, 100 g brown sugar, 2 eggs. Bake 60 min at 175 °C.""",
    "japanese_curry.md": """
# Japanese curry
Chicken thighs, onions, carrots, potatoes, half a box of curry roux. Simmer 20 min, add grated apple.""",
    "kimchi_fried_rice.md": """
# Kimchi fried rice
Day-old rice, chopped kimchi with its juice, gochujang, spam or bacon, a fried egg on top.""",
    "蔥油餅.md": """
# 蔥油餅
中筋麵粉 300 g、熱水 180 g、蔥花一大碗、豬油。擀開抹油撒蔥捲起，再擀平煎到兩面金黃。""",
    "珍珠奶茶.md": """
# 珍珠奶茶
粉圓煮 30 分鐘燜 30 分鐘，泡黑糖。紅茶濃一點，加鮮奶比例 2:1。""",
    "cold_brew.md": """
# Cold brew coffee
100 g coarse ground coffee to 1 litre of cold water. Steep 14-16 hours in the fridge, filter, dilute 1:1.""",
    "鳳梨酥.md": """
# 鳳梨酥
內餡：土鳳梨 + 冬瓜醬。外皮：奶油 120 g、糖粉 30 g、蛋 1 顆、低筋麵粉 200 g、奶粉 30 g。170 度烤 20 分鐘。""",
    "綠豆湯.md": """
# 綠豆湯
綠豆 300 g 泡 2 小時，加水 2.5 公升煮到開花，關火後加二砂糖。冰的更好喝。""",
    "granola.md": """
# Granola
Oats, almonds, honey, coconut oil, cinnamon. 150 °C for 25 minutes, stir halfway.""",
    "miso_soup.md": """
# Miso soup
Dashi from kombu and bonito flakes, tofu cubes, wakame, two tablespoons of miso stirred in off the heat.""",
    "pad_thai.md": """
# Pad thai
Rice noodles soaked 30 min, tamarind paste, fish sauce, palm sugar, shrimp, bean sprouts, peanuts.""",
    "chicken_soup.md": """
# Chicken noodle soup
Whole chicken simmered 90 minutes with onion, carrot, celery, bay leaf. Shred the meat, add egg noodles.""",
    "煎餃.md": """
# 煎餃
高麗菜豬肉餡，包好後下鍋煎到底部金黃，加麵粉水蓋鍋燜 6 分鐘，做出冰花。""",
    "酸辣湯.md": """
# 酸辣湯
豆腐、木耳、筍絲、豬肉絲、蛋花，烏醋和白胡椒調酸辣，最後勾芡。""",
}


def recipes():
    for name, body in RECIPES.items():
        txt(f"Recipes/{name}", body)


# ---------------------------------------------------------------- Work
TOPICS = [
    ("the onboarding redesign", "Mia"), ("the billing migration", "Leo"), ("the mobile release 4.2", "Ivy"),
    ("the support ticket backlog", "Noah"), ("the analytics dashboard", "Leo"), ("the partner API", "Ava"),
    ("the search ranking experiment", "Ivy"), ("the GDPR data export", "Mia"), ("hiring a backend engineer", "Noah"),
    ("the status page", "Ava"), ("the referral programme", "Mia"), ("the Q2 budget", "Noah"),
]


def work():
    txt("Work/Q3_roadmap.md", """
# Q3 roadmap
1. Ship the new onboarding flow (owner: design + web).
2. Cut checkout latency below 300 ms at p95.
3. Pilot the self-serve invoice export with five customers.
Review dates: July 8, August 12, September 16.""")
    txt("Work/Q2_roadmap.md", """
# Q2 roadmap
1. Launch the mobile release 4.2 with offline mode.
2. Move billing to the new payment provider.
3. Reduce support first-response time to under 4 hours.""")
    txt("Work/Q4_roadmap_draft.md", """
# Q4 roadmap (draft)
1. Single sign-on for enterprise customers (SAML and OIDC).
2. Annual plans with a 15% discount.
3. Expand the status page to show regional incidents.""")
    txt("Work/Q1_roadmap.md", """
# Q1 roadmap
1. Rebuild the analytics dashboard on the new event pipeline.
2. Hire two backend engineers.
3. Partner API beta with three partners.""")
    txt("Work/meeting_notes_0612.md", """
# Weekly sync, June 12
Decisions: launch the pricing-page A/B test on June 20; move the data export to the Q3 roadmap.
Action items: draft the customer email (Mia), update the dashboard filters (Leo).""")
    txt("Work/meeting_notes_0619.md", """
# Weekly sync, June 19
Decisions: SSO migration owned by Ava, target end of September; freeze the old admin panel.
Action items: write the SAML test plan (Ava), collect enterprise customer list (Noah).""")
    days = [(1, 9), (1, 16), (1, 23), (1, 30), (2, 6), (2, 13), (2, 20), (2, 27), (3, 6), (3, 13), (3, 20), (3, 27),
            (4, 3), (4, 10), (4, 17), (4, 24), (5, 1), (5, 8), (5, 15), (5, 22), (5, 29), (6, 5)]
    months = ["", "January", "February", "March", "April", "May", "June"]
    for mo, d in days:
        a, b = R.sample(TOPICS, 2)
        txt(f"Work/meetings/meeting_notes_{mo:02d}{d:02d}.md", f"""
# Weekly sync, {months[mo]} {d}
Updates: {a[0]} is {R.choice(['on track', 'a week late', 'blocked on review', 'done'])}; {b[0]} {R.choice(['needs a decision', 'started', 'slipped', 'is in QA'])}.
Action items: follow up on {a[0]} ({a[1]}), share notes on {b[0]} ({b[1]}).""")
    customers = ["Northwind Traders", "Blue Harbor Cafe", "Lumen Labs", "Kestrel Logistics", "Maple & Finch",
                 "Orbit Fitness", "Tidewater Books", "Copperleaf Studio", "Granite Health", "Summit Bikes"]
    for i, c in enumerate(customers):
        num = 2026_0100 + i * 7 + 3
        amt = R.randrange(18, 260) * 1000
        pdf(f"Work/invoices/INV-{num}.pdf", f"""
INVOICE INV-{num}
Bill to: {c}
Service: annual subscription, {R.choice(['Team', 'Business', 'Enterprise'])} plan
Amount: NT${amt:,} (tax included). Due within 30 days of {['January','February','March','April','May'][i % 5]} {R.randrange(1, 28)}, 2026.""")
    pptx("Work/Pricing_review.pptx", [
        ("Pricing review 2026", "Proposal: raise the Team plan from NT$290 to NT$330 per seat"),
        ("Why", "Churn is flat after the last increase; competitors charge NT$350-420"),
        ("Plan", "Grandfather existing customers for 12 months; announce on 1 September")])
    xlsx("Work/headcount_plan.xlsx", "2026", [
        ["Team", "Now", "End of 2026"], ["Backend", 6, 8], ["Frontend", 4, 5], ["Design", 2, 3], ["Support", 5, 5]])
    txt("Work/1on1_notes.md", """
# 1:1 notes
Wants to grow into tech lead. Next step: lead the partner API design review. Check in again in August.""")
    txt("Work/OKR_2026H1.md", """
# OKR 2026 H1
O1 Make onboarding effortless. KR: activation from 38% to 50%. KR: time-to-first-report under 10 min.
O2 Reliable platform. KR: 99.95% uptime. KR: p95 API latency under 250 ms.""")
    txt("Work/incident_2026-03-04.md", """
# Incident 2026-03-04: login outage
Duration 47 minutes. Cause: expired TLS certificate on the auth service. Fix: automated renewal and an expiry alert 14 days ahead.""")
    docx("Work/年終檢討.docx", "2025 年終檢討", [
        "今年完成：新版報表、帳單系統搬遷、客服回覆時間縮短到 3.5 小時。",
        "沒做好：行動版 4.2 延期兩個月；文件跟不上功能。",
        "明年重點：企業版單一登入、年繳方案。"])
    screenshot("Work/Screenshot 2026-05-20 at 15.02.11.png", """
Error 502: Bad Gateway
upstream timed out while reading response header
request id 7f3c-91ab
api.example.internal /v2/reports/export""", phone=False)


# ---------------------------------------------------------------- Study, Health, Notes, Car
def study():
    notes = {
        "transformer_notes.md": "# Transformer notes\nSelf-attention: softmax(QK^T / sqrt(d)) V. Multi-head attention runs several in parallel. Positional encodings add order.",
        "線性代數筆記.md": "# 線性代數筆記\n特徵值與特徵向量：Av = λv。對稱矩陣可以正交對角化。SVD 把任何矩陣拆成 UΣV^T。",
        "統計_假設檢定.md": "# 假設檢定\n虛無假設、p 值、型一錯誤 α、型二錯誤 β。p < 0.05 不代表效果大。",
        "N3單字.md": "# 日文 N3 單字\n予約（よやく）預約、遅刻（ちこく）遲到、片付ける（かたづける）整理、払う（はらう）付錢。",
        "rag_paper_notes.md": "# Retrieval-augmented generation\nDense retriever + generator. Hybrid retrieval (BM25 + vectors) helps on rare terms and IDs.",
        "cnn_notes.md": "# CNN notes\nConvolution shares weights across positions. Pooling reduces resolution. ResNet adds skip connections.",
        "作業系統_排程.md": "# 作業系統：CPU 排程\nFCFS、SJF、Round Robin（時間片）、優先權排程。Round Robin 的時間片太短會增加切換成本。",
        "sql_cheatsheet.md": "# SQL cheatsheet\nLEFT JOIN keeps unmatched rows. GROUP BY with HAVING filters groups. Window functions: ROW_NUMBER() OVER (PARTITION BY ...).",
        "經濟學_供需.md": "# 經濟學：供需\n價格上限低於均衡價格會造成短缺。需求彈性大的商品，漲價會讓總收入下降。",
        "git_tips.md": "# Git tips\ngit rebase -i to squash, git bisect to find the commit that broke a test, git worktree for parallel branches.",
    }
    for name, body in notes.items():
        txt(f"Study/{name}", body)
    pdf("Study/ML_midterm_review.pdf", """
Machine learning midterm review
Bias-variance trade-off; regularisation (L1 makes weights sparse, L2 shrinks them).
Cross-validation: k-fold. Gradient descent learning rate too high diverges.""")


def health():
    pdf("Health/健檢報告_2025.pdf", """
2025 年度健康檢查報告
總膽固醇 212 mg/dL（偏高），三酸甘油酯 135，空腹血糖 92。
建議：減少油炸食物，每週運動 150 分鐘，一年後追蹤。""")
    scan("Health/健檢報告_2026.pdf", """
2026 年度健康檢查報告
總膽固醇 188 mg/dL（正常）
三酸甘油酯 110　空腹血糖 90
血壓 118/76
醫師建議：維持目前運動習慣""")
    screenshot("Health/IMG_7002.png", """
牙科診所 預約提醒
洗牙 + 檢查
2026 年 7 月 9 日（四）下午 3:30
請提前 10 分鐘報到""")
    txt("Health/過敏藥.txt", """
過敏藥：每天睡前一顆，連續服用 7 天。症狀改善後不用繼續吃。避免與酒精併用。""")
    txt("Health/workout_plan.md", """
# Workout plan
Mon: squats 5x5, bench 5x5. Wed: deadlift 3x5, pull-ups. Fri: overhead press, rows. Run 5 km on Sunday.""")


def notes():
    txt("Car/保養紀錄.md", """
# 汽車保養紀錄
2025/11/02 25,000 km 換機油、機油濾芯。
2026/05/10 32,000 km 換機油、煞車油、雨刷。下次保養 37,000 km 或 2026 年 11 月。""")
    txt("Car/scooter_maintenance.md", """
# Scooter maintenance
Oil change every 1,000 km. Last one 3 March 2026 at 8,420 km. Rear tyre replaced in January.""")
    pdf("Car/行照影本.pdf", """
行車執照（影本）
車種：自用小客車　出廠年月：2021 年 4 月
下次定期檢驗日期：2026 年 4 月 30 日""")
    txt("Notes/gift_ideas.md", """
# Gift ideas
Mum: a good hand cream, a scarf. Dad: a pour-over coffee set. Sister: concert tickets.""")
    txt("Notes/books_2026.md", """
# Books 2026
Finished: a history of the spice trade; a novel about a lighthouse keeper. Reading: a book on habits.""")
    txt("Notes/wifi_and_devices.md", """
# Devices at home
Router in the living room, mesh node upstairs. Printer IP 192.168.1.40. NAS backup every Sunday 03:00.""")
    txt("Notes/待辦.md", """
# 待辦
- 繳房屋稅（5 月底前）
- 預約洗牙
- 更新護照
- 回覆房東修繕""")
    entries = [
        "今天去河濱騎腳踏車，風很大，回程差點騎不動。",
        "Tried the new ramen place near the station; broth too salty, noodles great.",
        "開會開到快五點，晚上決定不加班，去看了一部電影。",
        "Rainy Sunday. Repotted the monstera and cleaned the balcony.",
        "朋友結婚，紅包包了 3,600。婚宴在中山區。",
        "Ran 10 km for the first time this year. Knees fine.",
        "整理衣櫃，捐了兩大袋衣服。",
        "Long call with the landlord about the leaking kitchen tap; plumber coming Thursday.",
        "颱風假，在家煮了綠豆湯。",
        "Learned how to make cold brew; too strong at first, 1:1 dilution works.",
    ]
    for i, e in enumerate(entries):
        txt(f"Notes/journal/2026-0{i % 6 + 1}-{10 + i}.md", e)
    words = ["project", "idea", "list", "notes", "draft", "plan", "記事", "想法", "草稿", "清單", "untitled", "misc"]
    fillers = [
        "Remember to call back about the order.", "會議前把資料印出來。", "Check whether the library book is due.",
        "下週三前回信。", "Buy batteries and light bulbs.", "整理照片備份到外接硬碟。", "Look up train times for the weekend.",
        "提醒自己多喝水。", "Draft for the newsletter, not sent.", "週末大掃除。", "Ideas: a reading nook by the window.",
        "影印身分證正反面。", "Return the parcel before Friday.", "家裡衛生紙快用完了。", "Try the bakery on the corner.",
    ]
    for i in range(70):
        name = f"{R.choice(words)}_{R.randrange(1, 300)}.{R.choice(['txt', 'md'])}"
        txt(f"Notes/misc/{i:02d}_{name}", "\n".join(R.sample(fillers, 3)))


def main():
    global OUT
    OUT = os.path.abspath(sys.argv[1])
    if os.path.exists(OUT):
        shutil.rmtree(OUT)
    for part in (home, finance, travel, recipes, work, study, health, notes):
        part()
    n = sum(len(f) for _, _, f in os.walk(OUT))
    print(f"{n} files in {OUT}")


if __name__ == "__main__":
    main()
