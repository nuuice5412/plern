# Spi Music — Music Streaming Web App (SQL Server + Flask)

โปรเจกต์วิชา **Database**: เว็บแอปสตรีมมิ่งเพลงที่ทำงานบนฐานข้อมูล **Microsoft SQL Server**
โดยออกแบบ schema ตาม ER Diagram ของกลุ่ม (Peter Chen) และใช้ของจริงครบทั้ง
ตาราง, constraint, index, view, stored procedure, trigger, transaction

> ภาพหน้าจอทั้งหมดอยู่ใน [`docs/shots/`](docs/shots) — สร้างใหม่ได้ด้วย `python tools/screenshot.py`
> (`player.png` จับตอนกดเล่นเพลงจริง จึงไม่มีในสคริปต์)

---

## 1. ฟีเจอร์

| ฝั่งผู้ใช้ | รายละเอียด |
|---|---|
| หน้าแรก | เพลงยอดนิยม, รายชื่อศิลปิน, สถิติระบบ, ฟังล่าสุด, เพลย์ลิสต์ของฉัน |
| ค้นหา | ค้นจากชื่อเพลง / ชื่อศิลปิน / บทบาท (เช่น "Singer") |
| หน้าศิลปิน | ประวัติ, ผลงานทั้งหมดพร้อม "บทบาท" ของศิลปินในแต่ละเพลง, ศิลปินที่เคยร่วมงาน |
| หน้าดูทั้งหมด (`/songs`, `/artists`) | ปุ่ม “ดูทั้งหมด” ของแต่ละแถวบนหน้าแรก พาไปหน้ารายการเต็ม (ตารางเพลง / กริดศิลปิน) |
| หน้าเพลง | รายชื่อผู้เกี่ยวข้อง (นักร้อง/แต่งเพลง/โปรดิวเซอร์), สถิติ, เพิ่มเข้าเพลย์ลิสต์ |
| เพลย์ลิสต์ | สร้าง / ลบ / เพิ่มเพลง / ลบเพลง (เฉพาะเจ้าของ), ดูของคนอื่นได้แบบอ่านอย่างเดียว |
| ประวัติการฟัง | 100 รายการล่าสุด, เวลารวม, ศิลปินที่ฟังบ่อย (กราฟแท่ง) |
| Player | เล่น/หยุด, ต่อเพลงอัตโนมัติ, เลือกเวลา, ระดับเสียง, **สุ่มเพลง**, **เล่นซ้ำ (ทั้งหมด/เพลงเดียว)**, **ขยายเป็นหน้าจอเต็ม** (กด ⤢ หรือคลิกที่ปก, ปิดด้วย Esc), คีย์บอร์ด Spacebar |
| ปุ่มเล่นในรายการเพลง | ไอคอน **สีขาวล้วน ไม่มีพื้นหลัง** — ชี้แถวเห็น ▶, เพลงที่กำลังเล่นเห็นแท่งเสียง 4 แท่งเคลื่อนไหว, และชี้ที่แถวที่กำลังเล่นจะเปลี่ยนเป็น ⏸ เพื่อกดหยุด |
| สมัคร/เข้าสู่ระบบ | **อีเมล + รหัส OTP 6 หลัก** (ไม่ต้องตั้งรหัสผ่าน) หรือรหัสผ่านเดิม (PBKDF2-HMAC-SHA256 + salt), session cookie |

**บัญชีทดลอง** (รหัสผ่านทุกคน `demo1234`): `demo` · `napat` · `ploy`
(หน้า login มีปุ่มเติมให้อัตโนมัติ)

---

## 2. เริ่มใช้งาน (3 ขั้น)

```powershell
# 1) เปิด PowerShell ที่โฟลเดอร์โปรเจกต์
cd C:\Users\IMOS\Documents\Spi

# 2) รันสคริปต์เดียวจบ (ติดตั้ง venv + สร้าง DB + สร้างไฟล์เสียง + เปิดเว็บ)
powershell -ExecutionPolicy Bypass -File .\run.ps1
```

เสร็จแล้วเปิด <http://127.0.0.1:5000>

ถ้าต้องการล้างฐานข้อมูลใหม่ทั้งหมด:

```powershell
.\run.ps1 -Reset
```

### เงื่อนไขของเครื่อง
- SQL Server (ทดสอบบน **SQL Server 2025 Express**, instance `.\SQLEXPRESS`)
- Windows Authentication (ผู้ใช้ปัจจุบันเป็น sysadmin) — เปลี่ยน instance ได้ด้วย `MSSQL_SERVER`
- Python 3.10 ขึ้นไป, ไดรเวอร์ **ODBC Driver 18 for SQL Server**
- ครั้งแรกต้องต่ออินเทอร์เน็ตเพื่อ `pip install` (Flask, pyodbc, requests)

### ถ้าไม่ใช้ run.ps1

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python tools\init_db.py      # สร้าง/รีเซ็ตฐานข้อมูล + seed
.\.venv\Scripts\python tools\gen_audio.py    # สร้างไฟล์เสียง (ครั้งเดียวพอ)
.\.venv\Scripts\python run.py                # เปิดเว็บ
```

---

## 3. โครงสร้างโปรเจกต์

```
Spi/
├── run.ps1                    # เปิดเว็บ + ตั้งค่าอัตโนมัติ
├── run.py                     # จุดเริ่มต้น Flask
├── requirements.txt
├── db/
│   ├── 01_schema.sql          # CREATE DATABASE + 8 ตาราง + constraint + index + trigger
│   ├── 02_seed.sql            # ข้อมูลตั้งต้น (11 ศิลปิน, 24 เพลง, 500 ประวัติฟัง)
│   └── 03_views_procs.sql     # 4 view + 5 stored procedure
├── app/
│   ├── __init__.py            # application factory, template filters
│   ├── config.py              # ค่าตั้งต้น (connection string จาก env)
│   ├── db.py                  # data access layer (query / call_proc / แปลง error ไทย)
│   ├── auth.py                # hash/verify รหัสผ่าน + @login_required
│   ├── routes.py              # ทุก route
│   ├── templates/             # base, index, search, song, artist, playlist, history, ...
│   └── static/
│       ├── css/style.css      # ธีมมืด
│       ├── css/fonts.css      # @font-face (สร้างโดย tools/fetch_fonts.py)
│       ├── fonts/             # Inter + Noto Sans Thai (.woff2, ~202 KB)
│       ├── js/player.js       # ตัวเล่นเพลง (vanilla JS)
│       ├── audio/             # song_<id>.m4a (ต้นฉบับ AAC) + manifest.json
│       └── img/               # cover_<id>.jpg / artist_<id>.jpg + manifest.json
├── tools/
│   ├── init_db.py             # รันสคริปต์ SQL ตามลำดับ (แยก batch ตาม GO)
│   ├── sync_catalog.py        # เพิ่มศิลปิน/เพลงจาก iTunes เข้าฐานข้อมูล
│   ├── fetch_previews.py      # ดึงพรีวิว 30 วิจาก iTunes + สร้าง manifest
│   ├── fetch_originals.py     # ใช้ไฟล์ต้นฉบับ .m4a (คุณภาพสูงสุด ไม่แปลง)
│   ├── compress_audio.py      # ย่อพรีวิว .m4a -> .mp3 (PyAV/ffmpeg)
│   ├── fetch_artwork.py       # ดึงปกเพลง (iTunes) + รูปศิลปิน (Deezer)
│   ├── fetch_fonts.py         # ดาวน์โหลดฟอนต์มาเก็บในเครื่อง (self-hosted)
│   ├── gen_audio.py           # สังเคราะห์ไฟล์เสียงสำรอง (.wav)
│   ├── demo_live_db.py        # สาธิต: แก้ข้อมูลใน DB -> หน้าเว็บเปลี่ยนทันที
│   ├── smoke_test.py          # ทดสอบ end-to-end 55 เคส ผ่าน HTTP
│   └── screenshot.py          # จับภาพหน้าเว็บไว้ทำรายงาน
└── docs/shots/                # รูปหน้าเว็บ
```

---

## 4. ER Diagram → ตารางจริง

| Entity (ER) | ตาราง | คีย์ / constraint ที่สำคัญ |
|---|---|---|
| USER | `[User]` | PK `UserID`, UNIQUE `Username`, UNIQUE `Email`, CHECK `Gender` |
| PLAYLIST | `Playlist` | PK `PlaylistID`, FK → `[User]` (ON DELETE CASCADE), UNIQUE (`UserID`,`PLname`) |
| SONG | `Song` | PK `SongID`, CHECK `Duration > 0`, CHECK `PlayCount >= 0` |
| PLAYLIST_DETAIL | `Playlist_Detail` | PK (`PlaylistID`,`SongID`), UNIQUE (`PlaylistID`,`TrackNo`) |
| HISTORY | `History` | PK `HistoryID`, FK → `[User]`, FK → `Song` |
| ARTIST | `Artist` | PK `ArtistID`, UNIQUE `ArtistName` |
| ROLE | `[Role]` | PK `RoleID`, UNIQUE `Role` |
| SONG_ARTIST_ROLE | `Song_Artist_Role` | PK (`SongID`,`ArtistID`,`RoleID`) — ternary relationship |

**สิ่งที่ ER วาดไว้แล้วเราไม่ได้เก็บเป็นคอลัมน์**

- `Song_Amount`, `Total_Time` บน PLAYLIST เป็น *derived attribute* (oval เส้นประ)
  → คำนวณสดใน `vw_PlaylistSummary` ด้วย `COUNT` / `SUM`
- `PlayCount` บน SONG เป็นค่าที่มาจาก HISTORY → เก็บเป็นคอลัมน์จริง **โดยเจตนา**
  (denormalize) แล้วรักษาความถูกต้องด้วย trigger

> `[User]` และ `[Role]` ต้องครอบด้วยวงเล็บเหลี่ยม เพราะ `USER` เป็นคำสงวนของ T-SQL

---

## 5. จุดออกแบบที่อธิบายในห้องสอบได้

### 5.1 ทำไม `PlayCount` เก็บซ้ำได้ แต่ `Song_Amount` ไม่เก็บ
หน้าแรกต้องเรียง "เพลงยอดนิยม" ทุกครั้งที่เปิด ถ้า `COUNT(*)` จาก `HISTORY`
(ซึ่งโตขึ้นเรื่อย ๆ) ต้นทุนจะเพิ่มตามจำนวนประวัติ — จึงเก็บ `PlayCount` ซ้ำ
แล้วใช้ **trigger** รักษาความถูกต้อง (เขียนแบบ set-based รองรับ insert หลายแถว):

```sql
CREATE TRIGGER dbo.trg_History_UpdatePlayCount ON dbo.History AFTER INSERT AS
BEGIN
    SET NOCOUNT ON;
    UPDATE s SET s.PlayCount = s.PlayCount + x.cnt
    FROM dbo.Song AS s
    JOIN (SELECT SongID, COUNT(*) AS cnt FROM inserted GROUP BY SongID) AS x
      ON x.SongID = s.SongID;
END
```

ในทางกลับกัน `Song_Amount`/`Total_Time` ของเพลย์ลิสต์ถูกอ่านน้อยกว่ามาก
และเปลี่ยนทุกครั้งที่เพิ่ม/ลบเพลง จึงปล่อยให้คำนวณสดใน view ดีกว่า (ไม่มี update anomaly)

### 5.2 ทำไมต้องมีตาราง `Song_Artist_Role` (ternary)
เพลงหนึ่งเพลงมีหลายคนเกี่ยวข้อง และคนเดียวกันมีหลายบทบาทในเพลงเดียว
(เช่น Nova Lane เป็นทั้ง Singer, Composer และ Producer ใน *Paper Lanterns*)
ถ้าเอา `ArtistID` ไปไว้ใน `Song` ตรง ๆ จะเก็บได้แค่ศิลปินคนเดียว
และตอบคำถาม "ใครเป็นคนแต่งเพลงนี้" ไม่ได้

ในทางกลับกัน เพลงคอลแลบจะติดศิลปินหลายคนพร้อมกันได้ เช่น
"เขียว เหลือง แดง (Get high)" มีทั้ง `PUN` และ `The Toys` เป็น Singer
`vw_SongDetail` จึงมีคอลัมน์ `ArtistList` (STRING_AGG ของ Singer + Featured)
ให้หน้าเพลงแสดงชื่อได้ครบแบบ "PUN, The Toys" ขณะที่รายการเพลงยังใช้
`MainArtistName` (ศิลปินหลักคนเดียว) เพื่อไม่ให้ตารางรก

เครดิตศิลปินในฐานข้อมูลถูกตรวจเทียบกับ `matchedArtist` ที่ iTunes คืนมาแล้ว
(`tools/fetch_previews.py` เก็บค่านี้ไว้ใน manifest) — เพลงคอลแลบทั้ง 6 เพลง
และศิลปินรับเชิญที่มี `feat.` ในชื่อเพลง ถูกผูกครบแล้ว

### 5.3 ลำดับเพลงในเพลย์ลิสต์ (`TrackNo`)
- เพิ่มเพลง → ต่อท้ายด้วย `MAX(TrackNo) + 1` (ใน `usp_Playlist_AddSong`)
- ลบเพลง → **ไม่** re-number เพราะจะชน `UNIQUE (PlaylistID, TrackNo)` ระหว่าง update
- ช่องว่างของ `TrackNo` ถูกกลบตอนแสดงผลด้วย `ROW_NUMBER()` ใน `vw_PlaylistTrackList`

### 5.4 Security ที่ทำจริง
- รหัสผ่าน: `PBKDF2-HMAC-SHA256`, 200,000 รอบ, salt สุ่มต่อคน → เก็บในคอลัมน์ `Password`
  รูปแบบ `pbkdf2_sha256$200000$<salt>$<hash>` (เทียบด้วย `hmac.compare_digest`)
- SQL Injection: ทุกค่าจากผู้ใช้ส่งเป็น parameter `?` ไม่ต่อสตริง SQL
- สิทธิ์: เพลย์ลิสต์แก้ไขได้เฉพาะเจ้าของ (403), หน้าส่วนตัวบังคับ login
- กัน open redirect ที่ `?next=` (รับเฉพาะ path ที่เริ่มด้วย `/` เดี่ยว)

### 5.5 index
FK ใน SQL Server ไม่ได้สร้าง index ให้อัตโนมัติ จึงเพิ่มเองตาม query ที่ใช้จริง
เช่น `IX_History_User_PlayedAt (UserID, Played_At DESC) INCLUDE (SongID)`
สำหรับหน้า "ประวัติการฟัง" และ `IX_Song_PlayCount (PlayCount DESC)` สำหรับ top songs

### 5.6 ฟอนต์ (ทำไมไม่ใช้ฟอนต์ของ Tidal)
Tidal ใช้ฟอนต์ proprietary ของเขาเอง เอามาแจกจ่ายในโปรเจกต์ไม่ได้ตามลิขสิทธิ์
จึงเลือกคู่ที่ใกล้เคียงที่สุดและเป็น **SIL Open Font License**:

- **Inter** — ละติน (grotesque แนวเดียวกับ UI ของ Tidal)
- **Noto Sans Thai** — ไทย (จับคู่กับ Inter ได้เนียน)

ติดตั้งด้วย `python tools/fetch_fonts.py` ซึ่งดาวน์โหลด `.woff2` มาเก็บที่
`app/static/fonts/` แล้วสร้าง `app/static/css/fonts.css` ให้ — **ไม่พึ่ง CDN**
จึงเปิดเดโมตอนไม่มีเน็ตได้และไม่ช้าลงจากการต่อ DNS ภายนอก (รวม ~202 KB)

ปรับ typography ให้ใกล้ Tidal: หัวเรื่อง letter-spacing ติดลบเล็กน้อย,
label ตัวพิมพ์ใหญ่ tracking กว้าง (`.eyebrow` = 0.24em), และเพิ่ม `line-height`
เป็น 1.62 เพราะอักษรไทยมีสระบน/ล่างที่ต้องการพื้นที่มากกว่าละติน

### 5.7 Player: แถบล่าง + หน้าจอเต็มจอ
`player.js` จัดการสองหน้าจอพร้อมกัน (แถบเล่นเพลงด้านล่าง และหน้าจอ "กำลังเล่น" เต็มจอ)
โดยให้ `syncUI()` เป็นที่เดียวที่อัปเดตทั้งคู่ — ปก, ชื่อเพลง, ศิลปิน, ป้ายพรีวิว, ลิงก์
จึงไม่มีทางที่สองหน้าจอแสดงข้อมูลไม่ตรงกัน

- **ขยาย/ย่อ**: ปุ่ม ⤢ ในแถบล่าง, คลิกที่ปก, หรือกด `Esc` เพื่อย่อ
- **เต็มหน้าจอเบราว์เซอร์**: ปุ่ม ⛶ ใช้ Fullscreen API (`requestFullscreen`)
- **สุ่มเพลง (`shuffleOn`)**: เลือก index ถัดไปแบบสุ่มโดยไม่ซ้ำเพลงเดิม
- **เล่นซ้ำ (`repeatMode`)**: `off → all → one` — ค่า `one` จะเล่นเพลงเดิมซ้ำเมื่อจบ
- **คิวเพลง**: ปุ่ม ☰ เปิดแผงรายการที่กำลังเล่น (ไฮไลต์เพลงปัจจุบัน คลิกเพื่อข้ามเพลง)
- **พื้นหลังหน้าจอเต็ม**: ใช้ปกเพลงเดียวกันทำ blur + saturate + brightness
  แล้วซ้อน gradient มืดด้านล่าง เพื่อให้ตัวหนังสืออ่านได้ทุกสีปก
- ลิงก์ **เปิดหน้าเพลง / เครดิต** (ชี้ไป `#credits` ซึ่งเป็นส่วน `SONG_ARTIST_ROLE`)
- **แถบเวลา** อยู่แถวล่างใต้ปุ่มควบคุม จัดกลางกว้าง 860px (เวลาชิดหัว-ท้ายของแถบ)
  ให้สัดส่วนใกล้แถบเล่นเพลงของ Tidal — ไม่ยืดเต็มจอจนดูยาวเกิน
- **แท็บ "เครดิต"** เปิดดูเครดิตในหน้าจอเต็มได้เลย **ไม่ต้องออกไปหน้าเพลง**
  (ดึงจาก `GET /api/song/<id>` ซึ่งอ่าน `SONG_ARTIST_ROLE` + ปีที่ออก + จำนวนครั้งที่เล่น)
  แสดงเรียงแบบ Tidal: โปรดิวเซอร์ → แต่งเพลง → เนื้อร้อง → ศิลปินรับเชิญ → นักร้อง
  กดซ้ำเพื่อปิด และ `Esc` ปิดแท็บก่อนแล้วจึงย่อหน้าจอ
- **ระดับเสียงจำค่าไว้** ใน `localStorage` (คีย์ `spi-music:volume`) จึงคงอยู่แม้รีเฟรชหน้า
  หรือปิดเบราว์เซอร์แล้วเปิดใหม่ — อ่านค่าไม่ได้ (เช่น โหมดส่วนตัว) ก็ถอยไปใช้ 0.8
- ความคืบหน้า/ระดับเสียง ของสองหน้าจอผูกกัน (ปรับที่ไหนอีกที่หนึ่งขยับตาม)

---

### 5.8 เข้าสู่ระบบด้วยอีเมล (OTP) — ตาราง `EmailCode`
แอปฟังเพลงส่วนใหญ่ให้กรอกแค่อีเมลแล้วส่งรหัสมา ระบบนี้ทำแบบเดียวกัน:

1. `/register` รับ **อีเมลอย่างเดียว**
2. ถ้าอีเมล **เคยสมัครแล้ว** → ส่งรหัสแล้วพาไปหน้ากรอกรหัสทันที (โหมดเข้าสู่ระบบ)
   ถ้าเป็น **อีเมลใหม่** → ไปหน้า `/register/details` กรอกให้ครบตามตาราง `USER`:
   **Username, Password (เก็บเป็น PBKDF2 hash), Gender, Date_of_Birth, Country, Tel**
   + ยอมรับข้อกำหนด (ต้องอายุ 13 ปีขึ้นไป · Username ต้องไม่ซ้ำ · รหัสผ่าน ≥ 8 ตัว)
3. `/auth/code` แสดงอีเมลแบบปิดบัง (`r***4@g****l.com`) + **ช่องกรอกรหัส 6 ช่อง**
   (พิมพ์แล้วเลื่อนช่องอัตโนมัติ, Backspace ย้อนกลับ, วางทั้งชุดได้)
   + ปุ่ม **ส่งรหัสใหม่** ที่นับถอยหลัง 60 วินาที
4. รหัสเก็บใน `dbo.EmailCode` (1 รหัสต่ออีเมล, อายุ 10 นาที, ผิดได้ 5 ครั้ง) และถูกลบเมื่อใช้สำเร็จ

ตารางนี้อยู่นอก ER เดิม (เป็นส่วนขยายเพื่อรองรับ auth แบบไร้รหัสผ่าน)
`01_schema.sql` ไม่ลบมัน เพราะไฟล์ `04_email_code.sql` สร้างแบบ `IF NOT EXISTS`

```sql
CREATE TABLE dbo.EmailCode (
    Email NVARCHAR(255) PRIMARY KEY,
    Code CHAR(6) NOT NULL,
    ExpiresAt DATETIME2 NOT NULL,
    Attempts INT NOT NULL DEFAULT 0,
    CreatedAt DATETIME2 NOT NULL DEFAULT SYSDATETIME()
);
```

**การส่งอีเมลจริง** — ตั้ง environment variable 4 ตัว (Gmail ต้องเปิด 2-Step
Verification แล้วสร้าง App Password):

```powershell
set SMTP_HOST=smtp.gmail.com
set SMTP_PORT=587
set SMTP_USER=you@gmail.com
set SMTP_PASS=<App Password 16 ตัว>
```

ถ้าไม่ตั้งค่า จะเป็น **โหมดทดสอบ**: รหัสถูกพิมพ์ลงคอนโซลของเซิร์ฟเวอร์
(`[MAIL-DEV] รหัสสำหรับ ... = 123456`) เหมาะกับการเดโมในเครื่อง/ในห้องเรียน

---

## 6. Query ที่น่าสนใจ (ใช้ในโปรเจกต์จริง)

**ศิลปิน + จำนวนเพลง + ยอดฟัง** (ระวัง double count เพราะศิลปินมีหลายบทบาทต่อเพลง)

```sql
SELECT a.ArtistID, a.ArtistName, x.SongCount, x.TotalPlays
FROM dbo.Artist AS a
OUTER APPLY (
    SELECT COUNT(*) AS SongCount, ISNULL(SUM(s.PlayCount), 0) AS TotalPlays
    FROM (SELECT DISTINCT SongID FROM dbo.Song_Artist_Role WHERE ArtistID = a.ArtistID) AS d
    JOIN dbo.Song AS s ON s.SongID = d.SongID
) AS x
ORDER BY x.TotalPlays DESC;
```

→ ถ้า `JOIN` ตรง ๆ แล้ว `SUM(PlayCount)` ค่าจะถูกบวกซ้ำตามจำนวนบทบาท
จึงต้อง `DISTINCT SongID` ก่อน (`COUNT(DISTINCT ...)` ใช้กับ `SUM` ไม่ได้)

**บทบาทของศิลปินในแต่ละเพลง** (`STRING_AGG`, SQL Server 2017+)

```sql
SELECT vd.SongTitle, STRING_AGG(r.[Role], N', ') WITHIN GROUP (ORDER BY r.RoleID) AS Roles
FROM dbo.Song_Artist_Role AS sar
JOIN dbo.vw_SongDetail AS vd ON vd.SongID = sar.SongID
JOIN dbo.[Role] AS r ON r.RoleID = sar.RoleID
WHERE sar.ArtistID = 1
GROUP BY vd.SongID, vd.SongTitle;
```

**เวลารวมของเพลย์ลิสต์ แบบ HH:MM:SS** (`vw_PlaylistSummary`)

```sql
CONCAT(FLOOR(SUM(s.Duration) / 3600), N':',
       RIGHT(CONCAT(N'0', (SUM(s.Duration) % 3600) / 60), 2), N':',
       RIGHT(CONCAT(N'0',  SUM(s.Duration) % 60), 2))
```

**เรียก stored procedure ที่มี OUTPUT parameter ผ่าน pyodbc**

```python
db.call_proc("""
    DECLARE @added BIT;
    EXEC dbo.usp_Playlist_AddSong @PlaylistID = ?, @SongID = ?, @Added = @added OUTPUT;
    SELECT CAST(@added AS INT) AS Added;
""", (playlist_id, song_id))
```

---

## 7. การทดสอบ

```powershell
# ต้องเปิดเว็บไว้ก่อน (คนละหน้าต่าง)
.\.venv\Scripts\python tools\smoke_test.py
```

ทดสอบ 55 เคส ครอบคลุม: หน้าเว็บทั้งหมด, สิทธิ์การเข้าถึง, login/สมัคร,
การบันทึกการฟัง + ตรวจว่า `PlayCount` เพิ่มขึ้นจริงจาก trigger,
สร้าง/เพิ่ม/ลบเพลย์ลิสต์ผ่าน stored procedure, และ 404/403
จากนั้นลบข้อมูลที่ทดสอบสร้างขึ้นให้อัตโนมัติ

ผลล่าสุด: **55/55 ผ่าน**

```powershell
.\.venv\Scripts\python tools\screenshot.py    # เก็บภาพหน้าเว็บลง docs/shots
```

---

## 8. ไฟล์เสียง + ปกเพลง + รูปศิลปิน

เพลงทั้ง **175 เพลง (44 ศิลปิน)** ในฐานข้อมูลเป็น **เพลงจริง** — ไทย 37 คน
(Palmy, Cocktail, Three Man Down, Bodyslam, Klear, Tattoo Colour, Polycat,
Getsunova, Potato, Big Ass, Slot Machine, Paradox, The Toys, Jeff Satur,
Bowkylion, ฯลฯ) และสากล 7 คน (The Weeknd, Dua Lipa, Coldplay, Bruno Mars,
Billie Eilish, Laufey, Phum Viphurit)
ชื่อเพลง/ศิลปิน/ความยาว/ปีที่ออก มาจาก **iTunes Search API** โดยตรง
จึงดึงพรีวิว 30 วินาที (ตัวเดียวกับที่ Apple Music ใช้) มาเล่นได้ตรงชื่อเพลง

```powershell
.\.venv\Scripts\python tools\fetch_previews.py            # ดึงพรีวิวที่ยังไม่มี
.\.venv\Scripts\python tools\fetch_previews.py --dry-run  # ดูผลจับคู่ก่อน ไม่โหลดไฟล์
.\.venv\Scripts\python tools\fetch_previews.py --force    # ดึงใหม่ทับของเดิม
```

สคริปต์จะ

1. อ่าน `SongID`, `SongTitle`, `MainArtistName` จาก `vw_SongDetail`
2. ค้น iTunes (`country=TH`) แล้วให้คะแนนความคล้ายของชื่อเพลง (65%) + ศิลปิน (35%)
3. โหลดเฉพาะผลที่คะแนนถึงเกณฑ์ (default 0.68) เก็บเป็น `app/static/audio/song_<id>.m4a`
4. เขียน `app/static/audio/manifest.json` ว่าเพลงไหนใช้ไฟล์อะไร

`player.js` อ่าน manifest นี้ก่อน ถ้าเพลงไหนไม่มีใน manifest จะ fallback ไปใช้
`song_<id>.wav` ที่สร้างจาก `tools/gen_audio.py` (จึงไม่มีเพลงไหนกดเล่นแล้วเงียบ)
เพลงที่เล่นจากพรีวิวจะมีป้าย **“พรีวิว 30 วิ”** ขึ้นในแถบเล่นเพลง

### ปกเพลงและรูปศิลปิน

```powershell
python tools/fetch_artwork.py                 # ดึงที่ยังไม่มี
python tools/fetch_artwork.py --dry-run       # ดูผลจับคู่ก่อน
python tools/fetch_artwork.py --force         # ดึงใหม่ทับ
python tools/fetch_artwork.py --cover-size 600
```

| รูปแบบ | แหล่ง | วิธีได้มา |
|---|---|---|
| ปกอัลบั้ม | **iTunes Lookup API** | ใช้ `itunesTrackId` ที่ `fetch_previews.py` บันทึกไว้ → lookup ตรงตัว ได้ปกของอัลบั้มจริง ไม่ต้องเดา (ขอขนาด 300×300 จาก URL `…100x100bb.jpg`) |
| รูปศิลปิน | **Deezer Search Artist API** | ค้นชื่อศิลปิน → รับเฉพาะผลที่ชื่อคล้าย ≥ 0.80 → ในกลุ่มนั้นเลือกคนที่มี `nb_fan` มากที่สุด (กันศิลปินชื่อซ้ำคนละวง) → โหลด `picture_big` (500×500) |

ไฟล์ที่ได้: `app/static/img/cover_<SongID>.jpg`, `artist_<ArtistID>.jpg` และ
`app/static/img/manifest.json` (ปัจจุบัน **ปก 175 ไฟล์ + รูปศิลปิน 42 ไฟล์ ≈ 6.8 MB**)

`app/artwork.py` อ่าน manifest นี้แล้วส่งให้ template ผ่าน `cover_url(song_id)` /
`artist_photo_url(artist_id)` — ถ้ารูปไหนไม่มี (เช่นศิลปินรับเชิญที่ Deezer ไม่มีข้อมูล)
UI จะ fallback เป็น gradient + ตัวอักษรแรกโดยอัตโนมัติ **จึงไม่แตะ schema ของ ER เลย**

> **ลิขสิทธิ์**: พรีวิวและปกอัลบั้มเป็นงานมีลิขสิทธิ์ของเจ้าของสิทธิ์ ใบอนุญาตของ Apple
> อนุญาตให้ใช้เพื่อการโปรโมต/สาธิต จึงเหมาะกับเดโมส่งอาจารย์ในเครื่อง
> ถ้าจะเผยแพร่สาธารณะ (GitHub public / deploy จริง) ควรเปลี่ยนไปใช้เพลงและภาพ
> CC0/CC-BY เช่น Pixabay, Jamendo, Free Music Archive แล้วชี้ `manifest.json`
> ไปที่ไฟล์นั้นแทน

`Duration` ในฐานข้อมูลคือความยาวเต็มของเพลง (เช่น 4:27) แต่ไฟล์ที่เล่นเป็นพรีวิว 30 วิ
— player จึงแสดงเวลาจากไฟล์จริงเพื่อไม่ให้ Progress bar หลอก

---

## 9. ขยายแคตตาล็อกเพลง

ข้อมูลในฐานข้อมูลปัจจุบันมี **44 ศิลปิน / 175 เพลง** (ไทย 37 + สากล 7) ถ้าต้องการมากกว่านี้
ใช้ `sync_catalog.py` ดึงเพิ่มจาก iTunes ได้เลย — ข้อมูลจะถูกต้องและพรีวิวจะตามมาครบ

```powershell
python tools/sync_catalog.py --list-artists        # ดูรายชื่อศิลปินชุดเริ่มต้น
python tools/sync_catalog.py --dry-run             # ดูว่าจะเพิ่มอะไร ไม่เขียน DB
python tools/sync_catalog.py --per-artist 8 --plays 8
python tools/sync_catalog.py --artists "Palmy,Laufey,HYBS"
python tools/sync_catalog.py --artists "Dua Lipa" --country US   # สโตร์นอก TH
```

ขั้นตอนเพิ่มเพลงใหม่ (ทำครั้งเดียวจบ):

```powershell
python tools/sync_catalog.py           # 1) เพิ่มศิลปิน/เพลง + ประวัติการฟัง
python tools/fetch_previews.py         # 2) โหลดพรีวิว 30 วิ (เฉพาะที่ยังไม่มี)
python tools/fetch_originals.py        # 3) ใช้ไฟล์ต้นฉบับ .m4a (ไม่แปลงคุณภาพ)
python tools/fetch_artwork.py          # 4) ดึงปกเพลง + รูปศิลปิน
```

### เลือกคุณภาพเสียง

**ค่าที่ใช้อยู่ตอนนี้: ไฟล์ต้นฉบับจาก iTunes ทั้งหมด (ไม่เข้ารหัสซ้ำ)**

```powershell
python tools/fetch_originals.py        # ดาวน์โหลดต้นฉบับ .m4a (AAC ~271 kbps)
python tools/fetch_originals.py --force   # ดาวน์โหลดใหม่ทั้งหมด
```

| ทางเลือก | คำสั่ง | ขนาด (175 เพลง) | คุณภาพ |
|---|---|---|---|
| **ต้นฉบับ AAC 271 kbps** | `fetch_originals.py` | **~172 MB** | **ดีสุด — ไม่มีการเข้ารหัสซ้ำเลย** |
| mp3 192 kbps | `compress_audio.py --kbps 192 --refetch-original` | ~123 MB | ใกล้เคียงต้นฉบับ แต่ผ่านการแปลง 1 ครั้ง |
| mp3 128 kbps | `compress_audio.py --kbps 128 --refetch-original` | ~82 MB | พอใช้ (เคยใช้ค่านี้) |
| mp3 64 kbps | `compress_audio.py --kbps 64 --refetch-original` | ~41 MB | เล็กสุด แต่เสียงทึบ/แตก |

`compress_audio.py` ใช้ **PyAV** (pip install av) ซึ่งมี FFmpeg อยู่ในตัว จึงไม่ต้อง
ติดตั้ง ffmpeg แยก ถ้าไม่มี PyAV จะลองใช้ ffmpeg ในเครื่องให้อัตโนมัติ

> **สำคัญ**: การอัปเกรดคุณภาพต้อง **ดึงต้นฉบับใหม่** (`--refetch-original`) เสมอ
> เพราะการแปลง mp3 64 kbps ไปเป็น 128 kbps ไม่ได้คืนคุณภาพที่เสียไปแล้ว — ได้แค่ไฟล์ที่ใหญ่ขึ้น
> ส่วน `fetch_originals.py` ใช้ `previewUrl` ที่บันทึกไว้ใน manifest จึงได้ไฟล์เดิมเป๊ะ
> ไม่ต้องค้นหา iTunes ใหม่ (ไม่มีโอกาสจับคู่ผิดเพลง)

> หมายเหตุ: สโตร์ iTunes ไทย (country=TH) ไม่มีเพลงของศิลปินสากลบางคน
> ถ้าค้นแล้วไม่เจอ ให้ลอง `--country US`

---

## 10. ข้อจำกัด / งานที่ต่อได้

- **ยังไม่มีตาราง ALBUM** — ตาม ER ของกลุ่ม (เพลงผูกกับศิลปินโดยตรง)
  ถ้าจะเพิ่ม: สร้าง `Album(AlbumID, AlbumTitle, Release_Date, ArtistID)` แล้วใส่ `AlbumID` ใน `Song`
  (iTunes API ให้ `collectionName` มาด้วย ใช้เป็นข้อมูลตั้งต้นได้เลย)
- **เครดิตในตาราง `Song_Artist_Role`** เป็นข้อมูลประกอบการสาธิต
  (Singer/Composer/Producer ของศิลปินเดียวกัน) ไม่ได้อ้างอิงปกอัลบั้มจริงทุกเพลง
  ส่วนศิลปินรับเชิญมาจากชื่อเพลงที่มี “feat.” อยู่จริง
- ยังไม่มี pagination (ใช้ `TOP (100)`), ยังไม่มี full-text search (ใช้ `LIKE`)
- ยังไม่มี refresh token / rate limiting (เป็นเดโมวิชาเรียน)
- ยังไม่มี transaction หลายขั้นที่ต้อง atomic — ถ้าต้องการเพิ่ม ใช้
  `autocommit=False` แล้ว `commit()` / `rollback()` (ดูตัวอย่างใน `app/db.py`)

---

## 11. หลักฐาน: SQL ↔ Backend ↔ Frontend ต่อกันจริง

### 11.1 รัน SQL ตรง ๆ ได้ (ไม่ต้องผ่าน Python)
ไฟล์ `.sql` ทั้งสามเป็น T-SQL มาตรฐาน เปิดใน SSMS แล้วกด Execute ได้เลย
(บันทึกเป็น UTF-8 **with BOM** เพื่อให้ SSMS อ่านภาษาไทยถูกต้อง)

```powershell
sqlcmd -S .\SQLEXPRESS -E -C -f 65001 -i db\01_schema.sql
sqlcmd -S .\SQLEXPRESS -E -C -f 65001 -i db\02_seed.sql
sqlcmd -S .\SQLEXPRESS -E -C -f 65001 -i db\03_views_procs.sql
```

ผลที่ได้: **8 ตาราง · 4 view · 5 stored procedure · 1 trigger**

### 11.2 แก้ข้อมูลในฐานข้อมูล → หน้าเว็บเปลี่ยนทันที

```powershell
python tools/demo_live_db.py     # ต้องเปิดเว็บไว้ก่อน
```

สคริปต์จะสาธิตให้เห็นทีละขั้น:

1. อ่านชื่อเพลง/ยอดเล่นจาก DB → เปิดหน้าเว็บยืนยันว่าแสดงค่านั้น
2. `UPDATE dbo.Song SET SongTitle = ...` จาก SQL โดยตรง → เปิดหน้าเว็บใหม่ **เห็นชื่อใหม่ทันที**
   (ไม่ต้องรีสตาร์ตเซิร์ฟเวอร์)
3. คืนชื่อเดิม
4. `INSERT INTO dbo.History` 1 แถว → **trigger** บวก `PlayCount` → API และหน้าเว็บแสดงยอดใหม่ตรงกัน
5. ลบแถวทดสอบและคืนยอดเดิม

### 11.3 เส้นทางของข้อมูล (ไม่มีข้อมูล hardcode ในหน้าเว็บ)

```
เบราว์เซอร์
   │  GET /song/1
   ▼
Flask route  (app/routes.py)          ← ไม่มีข้อมูลเพลงเขียนไว้ในโค้ด
   │  execute("SELECT ... FROM dbo.vw_SongDetail WHERE SongID = ?")
   ▼
pyodbc  →  SQL Server (MusicStreamingDB)
   │  view / stored procedure / trigger
   ▼
Jinja template (app/templates/song.html)  ← แค่แสดงค่าที่ได้รับมา
```

จุดที่พิสูจน์ได้ว่าผูกกันจริง: ชื่อเพลงบนหน้าเว็บเปลี่ยนตาม `UPDATE` ทันที,
ยอด "ครั้งที่เล่น" เปลี่ยนตาม `INSERT` ลง `HISTORY` (ผ่าน trigger),
และทุกหน้าดึงจาก view (`vw_SongDetail`, `vw_PlaylistSummary`, `vw_TopSongs`, `vw_PlaylistTrackList`)

---

## 12. ให้เพื่อนทดสอบ

### วิธีที่ 1 — เพื่อนอยู่ใน Wi-Fi เดียวกัน (ง่ายที่สุด)
เครื่องนี้เปิดให้แล้ว: bind `0.0.0.0` + เปิด Windows Firewall (เฉพาะ Private network)

```
http://192.168.1.100:5000      ← ส่งลิงก์นี้ให้เพื่อน (ใช้ได้ทั้งมือถือ/โน้ตบุ๊ก)
```

เปิดเองด้วยคำสั่ง:

```powershell
set HOST=0.0.0.0
.\.venv\Scripts\python run.py
```

> IP อาจเปลี่ยนเมื่อรีสตาร์ตเราเตอร์ — ดูใหม่ด้วย `ipconfig` (ช่อง IPv4)
> ถ้าเพื่อนเข้าไม่ได้ ให้เช็คว่าอยู่ Wi-Fi เดียวกัน และ firewall เปิดเฉพาะ Private

ปิดช่องที่เปิดไว้ (ถ้าไม่ต้องการแล้ว):

```powershell
Remove-NetFirewallRule -DisplayName "Spi Music (Flask 5000)"
```

### วิธีที่ 2 — ขึ้นออนไลน์ทันทีด้วย Cloudflare Tunnel (ฟรี)

ไบนารีอยู่ในโปรเจกต์แล้วที่ `tools/bin/cloudflared.exe` — เปิด tunnel ได้เลย:

```powershell
# หน้าต่างที่ 1: เปิดเว็บ
.\.venv\Scripts\python run.py

# หน้าต่างที่ 2: เปิด tunnel (เครื่องต้องออนไลน์ตลอด)
.\tools\bin\cloudflared.exe tunnel --url http://localhost:5000
```

จะได้ URL แบบ `https://xxxx-xxxx.trycloudflare.com` ใช้ได้จากทุกที่ในโลก
(ปิดหน้าต่าง = ลิงก์ดับ, URL เปลี่ยนทุกครั้งที่เปิดใหม่)

> ข้อจำกัด: เครื่องต้องเปิดทิ้งไว้ · ความเร็วขึ้นกับอินเทอร์เน็ตอัปโหลดที่บ้าน
> (ไฟล์เสียงรวม ~170 MB) · ใครมีลิงก์ก็เข้าได้

### วิธีที่ 2.5 — ขึ้นออนไลน์แบบถาวร (ต้องมีที่อยู่ SQL Server)

ปัญหาหลัก: **SQL Server ไม่มี free tier บน cloud** (ต่างจาก MySQL/Postgres)

| ทางเลือก | ค่าใช้จ่าย | หมายเหตุ |
|---|---|---|
| **Azure for Students** + Azure SQL free tier + App Service | ฟรี (~$100 credit/ปี) | ตรงที่สุดเพราะยังเป็น SQL Server จริง |
| Render / Railway + SQL Server container | ต้องเสียเงิน (~$7+/เดือน, RAM 2GB) | ฟรี tier ไม่พอรัน SQL Server |
| เปลี่ยนไป PostgreSQL/MySQL | ฟรี | **ไม่แนะนำ** — ผิดโจทย์วิชา database ที่อาจารย์ตรวจ T-SQL |

### วิธีที่ 3 — ส่งไฟล์ให้เพื่อนรันเอง

```powershell
# บีบอัดทั้งโฟลเดอร์ ยกเว้น .venv (สร้างใหม่ได้)
# เพื่อนต้องมี: Windows + SQL Server Express + Python 3.10+ + ODBC Driver 18 for SQL Server
```

แล้วเพื่อนรัน `run.ps1` — สคริปต์จะสร้าง venv / สร้างฐานข้อมูล / เปิดเว็บให้เอง

> ข้อควรระวัง: ไฟล์เสียง `.m4a` 170 MB — ถ้าส่งผ่านอีเมลจะไม่ผ่าน ให้ใช้ Google Drive

### วิธีที่ 4 — แค่ให้ดู ไม่ต้องรัน
อัดวิดีโอหน้าจอ (Win + G) หรือใช้ภาพใน `docs/shots/` — เหมาะกับกรณีส่งรายงาน

### บัญชีสำหรับให้เพื่อนทดสอบ
`demo` · `napat` · `ploy` — รหัสผ่าน `demo1234` ทุกคน
(ในหน้า login มีปุ่มเติมบัญชีให้อัตโนมัติ)

> ความปลอดภัย: เป็นเดโมวิชาเรียน ทุกคนที่เข้าถึงเว็บได้จะแก้เพลย์ลิสต์ของ `demo` ได้
> ถ้าให้ทดสอบนาน ๆ ควรเปลี่ยนรหัสผ่าน หรือสร้างผู้ใช้ใหม่ให้เพื่อนโดยเฉพาะ

---

## 13. ขึ้น Git (GitHub) — ไฟล์เพลง 175 MB ใช้ Git LFS

repo ถูกติดตั้งไว้แล้ว: `git init` + `git lfs track "*.m4a" "*.wav"` + commit แรกเรียบร้อย

| ส่วน | ขนาด |
|---|---|
| ไฟล์โค้ด/เทมเพลต/ภาพ | **12.6 MB** |
| ไฟล์เสียง (Git LFS) | **175.3 MB** (199 ไฟล์) |

ใน commit จะเก็บเพลงเป็น **pointer** ไม่ใช่ไฟล์จริง:

```
version https://git-lfs.github.com/spec/v1
oid sha256:0184ab60...
size 1040903
```

> `tools/bin/cloudflared.exe` (52 MB) และ `.venv/` ถูก ignore ไว้แล้ว

### ขั้นตอน push (ทำครั้งเดียว)

```powershell
# 1) สร้าง repo เปล่า ๆ บน GitHub (ไม่ต้องติ๊ก Add README)
# 2) ผูก remote แล้ว push
git remote add origin https://github.com/<USER>/<REPO>.git
git push -u origin main
```

Git LFS จะอัปโหลดเพลงขึ้นเองอัตโนมัติ (รอบแรกอาจใช้เวลาหลายนาที เพราะ ~175 MB)

### โควตาฟรีของ GitHub LFS
- พื้นที่ 1 GB · แบนด์วิดท์ 1 GB/เดือน → โปรเจกต์นี้ใช้ ~175 MB
- ถ้ามีคนโคลนบ่อย ๆ แบนด์วิดท์จะหมดเร็ว (1 โคลน ≈ 175 MB)

### คนที่โคลน repo ไปต้องมี Git LFS

```powershell
git lfs install          # ติดตั้งครั้งเดียว
git clone https://github.com/<USER>/<REPO>.git
```

ถ้าไม่อยากโหลดเพลงตอนโคลน: `GIT_LFS_SKIP_SMUDGE=1 git clone ...`

### ทางเลือกถ้าไม่อยากใช้ LFS
อัปโหลดไฟล์เสียงเป็น **GitHub Release** (zip) แล้วให้สคริปต์ดาวน์โหลด — repo จะเหลือ ~13 MB
แต่ต้องรันสคริปต์เพิ่มก่อนใช้งาน และไฟล์เสียงจะไม่ถูก track ใน git history

---

## 14. ภาคผนวก: เปิดฐานข้อมูลด้วยเครื่องมืออื่น

```powershell
# ดูตารางทั้งหมด
sqlcmd -S .\SQLEXPRESS -E -C -d MusicStreamingDB -Q "SELECT name FROM sys.tables ORDER BY name"

# ดู 5 เพลงยอดนิยม
sqlcmd -S .\SQLEXPRESS -E -C -d MusicStreamingDB -Q "SELECT TOP 5 * FROM dbo.vw_TopSongs"

# ดู definition ของ view/procedure
sqlcmd -S .\SQLEXPRESS -E -C -d MusicStreamingDB -Q "EXEC sp_helptext 'dbo.usp_Playlist_AddSong'"
```

เปิดด้วย **SQL Server Management Studio (SSMS)** หรือ **Azure Data Studio**
แล้วเชื่อมต่อ `.\SQLEXPRESS` → Databases → `MusicStreamingDB`

ไฟล์ `.sql` ทั้งหมดเขียนเป็น UTF-8 และ comment ภาษาไทยอ่านได้
(ถ้าเปิดใน SSMS แล้วภาษาเพี้ยน ให้เลือก File → Open → File… แล้วเปลี่ยน Encoding เป็น UTF-8)

ถ้าแก้เฉพาะ view/procedure และไม่อยากล้างข้อมูลทั้งฐานข้อมูล:

```powershell
python tools/init_db.py --scripts 03      # รันเฉพาะ 03_views_procs.sql
```









