/* =====================================================================
   Music Streaming Database
   02_seed.sql : ข้อมูลตัวอย่างสำหรับ demo / ทดสอบ query

   *** ข้อมูลเพลงชุดนี้เป็นเพลงจริงที่ตรวจสอบแล้วว่ามีอยู่บน iTunes Store ***
   (ดึง metadata จาก iTunes Search API: ชื่อเพลง, ความยาว, วันที่วางจำหน่าย)
   ทำให้ไฟล์พรีวิว 30 วินาทีที่ดึงด้วย tools/fetch_previews.py ตรงกับชื่อเพลง
   และศิลปินในฐานข้อมูลจริง ไม่ใช่เพลงอื่นที่ชื่อคล้ายกัน

   หมายเหตุความถูกต้องของข้อมูล
   - ชื่อเพลง / ศิลปิน / ความยาว / ปีที่ออก = ข้อมูลจริงจาก iTunes
   - "บทบาท" (Singer/Composer/Producer) เป็นข้อมูลประกอบการสาธิต
     ไม่ได้อ้างอิงเครดิตจากปกอัลบั้มจริงทุกเพลง
   - ศิลปินรับเชิญ (Featured) มาจากชื่อเพลงที่มี "feat." อยู่จริง
   - ประวัติการฟัง (HISTORY) เป็นข้อมูลจำลองที่สร้างขึ้นเพื่อทดสอบสถิติ

   รันหลัง 01_schema.sql (ต้องมี trigger trg_History_UpdatePlayCount แล้ว
   เพื่อให้การ insert HISTORY ในไฟล์นี้บวก PlayCount ของ SONG ให้อัตโนมัติ)

   บัญชีทดลอง (รหัสผ่านทุกคน: demo1234)
     demo   / demo@example.com
     napat  / napat@example.com
     ploy   / ploy@example.com
   ===================================================================== */

USE MusicStreamingDB;
GO
SET NOCOUNT ON;
GO

/* ---------------------------------------------------------------------
   ARTIST (8 ศิลปินหลัก + 3 ศิลปินรับเชิญ)
   --------------------------------------------------------------------- */
SET IDENTITY_INSERT dbo.Artist ON;
INSERT INTO dbo.Artist (ArtistID, ArtistName, Country, Bio) VALUES
 (1, N'Palmy',              N'TH', N'นักร้องหญิงไทยเจ้าของเพลงฮิตต่อเนื่องหลายยุค ทำงานแนวป็อปและป็อปร็อก'),
 (2, N'Cocktail',           N'TH', N'วงป็อปร็อกไทยที่ก่อตั้งปี 2002 มีเพลงฮิตต่อเนื่องมาถึงปัจจุบัน'),
 (3, N'Three Man Down',     N'TH', N'วงอินดี้ป็อปไทยที่แจ้งเกิดจากเพลง “ถ้าเธอรักฉันจริง”'),
 (4, N'Phum Viphurit',      N'TH', N'ศิลปินไทยแนวมินิมอลป็อป/อินดี้ป็อป เจ้าของเพลง “Lover Boy”'),
 (5, N'Bodyslam',           N'TH', N'วงป็อปร็อกไทยที่ก่อตั้งปี 2002 มีเพลงฮิตในตำนานหลายเพลง'),
 (6, N'Klear',              N'TH', N'วงป็อปร็อกไทยที่มีเพลงฮิตในช่วงปี 2010s'),
 (7, N'Violette Wautier',   N'TH', N'นักร้องและนักแสดงลูกครึ่งไทย-เบลเยียม ทำงานเพลงอินดี้ป็อป'),
 (8, N'Whal & Dolph',       N'TH', N'ดูโออินดี้ป็อปไทยที่มีเอกลักษณ์ด้านเสียงประสาน'),
 (9, N'Q Flure',            N'TH', N'ศิลปินรับเชิญในเพลง “Yours Ever” ของ Cocktail'),
 (10, N'ออม TELEx TELEXs',   N'TH', N'นักร้องจากวง TELEx TELEXs รับเชิญในเพลง “ข้างกัน”'),
 (11, N'แอ๊ด คาราบาว',        N'TH', N'นักร้องนำวงคาราบาว รับเชิญในเพลง “ความเชื่อ” ของ Bodyslam');
SET IDENTITY_INSERT dbo.Artist OFF;
GO

/* ---------------------------------------------------------------------
   ROLE (บทบาทของศิลปินต่องานเพลง)
   --------------------------------------------------------------------- */
SET IDENTITY_INSERT dbo.[Role] ON;
INSERT INTO dbo.[Role] (RoleID, [Role], Role_desc) VALUES
 (1, N'Singer',    N'ผู้ขับร้อง / นักร้องหลักของเพลง'),
 (2, N'Featured',  N'ศิลปินรับเชิญ (feat.) ที่ร่วมร้องในเพลง'),
 (3, N'Composer',  N'ผู้แต่งทำนองและเรียบเรียงดนตรี'),
 (4, N'Lyricist',  N'ผู้เขียนเนื้อร้อง'),
 (5, N'Producer',  N'ผู้ควบคุมการผลิตและมิกซ์เสียง');
SET IDENTITY_INSERT dbo.[Role] OFF;
GO

/* ---------------------------------------------------------------------
   SONG (24 เพลงจริง = 8 ศิลปิน x 3 เพลง)
   Duration เป็นความยาวจริงหน่วยวินาที (จาก iTunes trackTimeMillis)
   PlayCount เริ่มที่ 0 แล้ว trigger จะบวกให้จาก HISTORY ด้านล่าง
   --------------------------------------------------------------------- */
SET IDENTITY_INSERT dbo.Song ON;
INSERT INTO dbo.Song (SongID, SongTitle, Duration, PlayCount, Released_Date) VALUES
 ( 1, N'หลุมอากาศ',                                        267, 0, '2026-06-17'),
 ( 2, N'ซ่อนกลิ่น',                                          252, 0, '2018-10-09'),
 ( 3, N'คิดมาก',                                            218, 0, '2011-12-09'),
 ( 4, N'คู่ชีวิต',                                            337, 0, '2014-10-02'),
 ( 5, N'โปรดเถิดรัก',                                        323, 0, '2013-09-12'),
 ( 6, N'Yours Ever (feat. Q Flure)',                        259, 0, '2024-08-29'),
 ( 7, N'ถ้าเธอรักฉันจริง',                                     240, 0, '2020-12-15'),
 ( 8, N'เพลงรัก',                                            269, 0, '2024-10-08'),
 ( 9, N'ข้างกัน (City) [feat. ออม TELEx TELEXs]',           296, 0, '2017-12-06'),
 (10, N'Lover Boy',                                          237, 0, '2018-03-22'),
 (11, N'Long Gone',                                          214, 0, '2017-02-04'),
 (12, N'Hello, Anxiety',                                     265, 0, '2019-03-22'),
 (13, N'ความเชื่อ (feat. แอ๊ด คาราบาว)',                      297, 0, '2005-04-22'),
 (14, N'ความรัก',                                            292, 0, '2010-05-11'),
 (15, N'ยาพิษ',                                              263, 0, '2007-09-18'),
 (16, N'คำยินดี',                                            267, 0, '2012-05-08'),
 (17, N'พันหมื่นเหตุผล',                                      266, 0, '2017-01-25'),
 (18, N'สิ่งของ',                                            274, 0, '2015-10-15'),
 (19, N'Smoke',                                              229, 0, '2018-10-26'),
 (20, N'จังหวะจะรัก',                                         220, 0, '2017-08-07'),
 (21, N'ยื้อเพื่อ? (Be Honest)',                             229, 0, '2022-10-31'),
 (22, N'ใจเดียว (Jai 1)',                                    229, 0, '2019-08-08'),
 (23, N'รอให้เธอบอก (Mute)',                                 279, 0, '2017-11-24'),
 (24, N'ไม่รู้ทำไม (Skyfall)',                               290, 0, '2019-02-14');
SET IDENTITY_INSERT dbo.Song OFF;
GO

/* ---------------------------------------------------------------------
   SONG_ARTIST_ROLE : ternary relationship (เพลง - ศิลปิน - บทบาท)

   ทุกเพลงมีศิลปินหลัก 1 คนใน 3 บทบาท (Singer/Composer/Producer)
   และเพลงที่มี "feat." มีศิลปินรับเชิญเพิ่มในบทบาท Featured
   => เพลงหนึ่งมีหลายศิลปิน และศิลปินหนึ่งอยู่หลายเพลง = M:N จริง
   --------------------------------------------------------------------- */
INSERT INTO dbo.Song_Artist_Role (SongID, ArtistID, RoleID) VALUES
 -- Palmy
 ( 1, 1,1),( 1, 1,3),( 1, 1,5),
 ( 2, 1,1),( 2, 1,3),( 2, 1,5),
 ( 3, 1,1),( 3, 1,3),( 3, 1,5),
 -- Cocktail
 ( 4, 2,1),( 4, 2,3),( 4, 2,5),
 ( 5, 2,1),( 5, 2,3),( 5, 2,5),
 ( 6, 2,1),( 6, 2,3),( 6, 2,5),
 ( 6, 9,2),                                   -- Q Flure (รับเชิญ)
 -- Three Man Down
 ( 7, 3,1),( 7, 3,3),( 7, 3,5),
 ( 8, 3,1),( 8, 3,3),( 8, 3,5),
 ( 9, 3,1),( 9, 3,3),( 9, 3,5),
 ( 9,10,2),                                   -- ออม TELEx TELEXs (รับเชิญ)
 -- Phum Viphurit
 (10, 4,1),(10, 4,3),(10, 4,5),
 (11, 4,1),(11, 4,3),(11, 4,5),
 (12, 4,1),(12, 4,3),(12, 4,5),
 -- Bodyslam
 (13, 5,1),(13, 5,3),(13, 5,5),
 (13,11,2),                                   -- แอ๊ด คาราบาว (รับเชิญ)
 (14, 5,1),(14, 5,3),(14, 5,5),
 (15, 5,1),(15, 5,3),(15, 5,5),
 -- Klear
 (16, 6,1),(16, 6,3),(16, 6,5),
 (17, 6,1),(17, 6,3),(17, 6,5),
 (18, 6,1),(18, 6,3),(18, 6,5),
 -- Violette Wautier
 (19, 7,1),(19, 7,3),(19, 7,5),
 (20, 7,1),(20, 7,3),(20, 7,5),
 (21, 7,1),(21, 7,3),(21, 7,5),
 -- Whal & Dolph
 (22, 8,1),(22, 8,3),(22, 8,5),
 (23, 8,1),(23, 8,3),(23, 8,5),
 (24, 8,1),(24, 8,3),(24, 8,5);
GO

/* ---------------------------------------------------------------------
   USER (3 คน)  Password = pbkdf2_sha256$<iter>$<salt>$<hash>
   ค่า hash ถูกคำนวณล่วงหน้าจากรหัสผ่าน demo1234 ด้วย PBKDF2-HMAC-SHA256
   200,000 รอบ (ดูวิธีตรวจสอบใน app/auth.py)
   --------------------------------------------------------------------- */
SET IDENTITY_INSERT dbo.[User] ON;
INSERT INTO dbo.[User] (UserID, Username, Password, Email, Gender, Date_of_Birth, Country, Tel) VALUES
 (1, N'demo',
     N'pbkdf2_sha256$200000$0ebdeedaeea3cc47b1e74c2e3844b67a$1f5042889668aba2517e7e013aa079cfe45506a69ef3e1794a1f849e7b190193',
     N'demo@example.com',  N'Male',   '2001-05-14', N'TH', N'0812345678'),
 (2, N'napat',
     N'pbkdf2_sha256$200000$801c4f9f7c7fc2d8fef248d26a94c895$c7cece3d4206cbc2395017fb2d2378c165ac8e3bde7357c3c4dab50c20b5cb56',
     N'napat@example.com', N'Female', '2003-01-30', N'TH', N'0898765432'),
 (3, N'ploy',
     N'pbkdf2_sha256$200000$c45c17d7b13d8bf4e3085b5932c64cac$57b33f65fb37671fbc190e0067abab2b9fc78370bc6007dc3548775e5b79140a',
     N'ploy@example.com',  N'Female', '2000-11-02', N'TH', N'0861112222');
SET IDENTITY_INSERT dbo.[User] OFF;
GO

/* ---------------------------------------------------------------------
   PLAYLIST + PLAYLIST_DETAIL
   --------------------------------------------------------------------- */
SET IDENTITY_INSERT dbo.Playlist ON;
INSERT INTO dbo.Playlist (PlaylistID, PLname, Create_Date, UserID) VALUES
 (1, N'สายฟังชิล',        '2025-01-15 20:14:00', 1),
 (2, N'เพลงไทยตอนดึก',    '2025-02-20 22:05:00', 1),
 (3, N'Drive Time',      '2025-03-05 07:30:00', 2),
 (4, N'อินดี้หน่อย',       '2025-04-11 18:45:00', 3),
 (5, N'เพลงเศร้า',        '2025-06-01 23:59:00', 3);
SET IDENTITY_INSERT dbo.Playlist OFF;
GO

INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, Date_Added, TrackNo) VALUES
 (1,  1, '2025-01-15 20:15:00', 1),
 (1, 19, '2025-01-15 20:16:00', 2),
 (1, 21, '2025-01-16 09:02:00', 3),
 (1, 10, '2025-01-18 21:40:00', 4),
 (1, 22, '2025-02-01 23:11:00', 5),
 (2,  3, '2025-02-20 22:06:00', 1),
 (2, 17, '2025-02-20 22:07:00', 2),
 (2, 16, '2025-02-22 19:20:00', 3),
 (2, 21, '2025-03-01 00:05:00', 4),
 (2, 23, '2025-03-01 00:06:00', 5),
 (3,  4, '2025-03-05 07:31:00', 1),
 (3,  5, '2025-03-05 07:32:00', 2),
 (3, 22, '2025-03-06 08:10:00', 3),
 (3, 24, '2025-03-06 08:11:00', 4),
 (3,  6, '2025-03-09 18:00:00', 5),
 (3, 11, '2025-03-09 18:01:00', 6),
 (3,  8, '2025-03-12 07:45:00', 7),
 (4,  1, '2025-04-11 18:46:00', 1),
 (4,  7, '2025-04-11 18:47:00', 2),
 (4, 18, '2025-04-12 20:30:00', 3),
 (4, 16, '2025-04-12 20:31:00', 4),
 (4, 10, '2025-04-15 22:00:00', 5),
 (5,  3, '2025-06-01 23:59:00', 1),
 (5,  5, '2025-06-02 00:02:00', 2),
 (5, 23, '2025-06-02 00:03:00', 3),
 (5, 21, '2025-06-03 22:15:00', 4);
GO

/* ---------------------------------------------------------------------
   HISTORY : ประวัติการเล่น ~500 ครั้ง กระจายย้อนหลัง 21 วัน
   ใช้ ROW_NUMBER() จับคู่ user/song แบบ deterministic (ไม่ต้องใช้ NEWID
   เพื่อให้รันซ้ำได้ผลเท่าเดิม และอ่านผลลัพธ์ง่าย)
   PlayCount ของ SONG จะถูก trigger บวกให้อัตโนมัติหลังบล็อกนี้
   --------------------------------------------------------------------- */
DECLARE @Users TABLE (rn INT PRIMARY KEY, UserID INT NOT NULL);
INSERT INTO @Users (rn, UserID)
SELECT ROW_NUMBER() OVER (ORDER BY UserID), UserID FROM dbo.[User];

DECLARE @Songs TABLE (rn INT PRIMARY KEY, SongID INT NOT NULL);
INSERT INTO @Songs (rn, SongID)
SELECT ROW_NUMBER() OVER (ORDER BY SongID), SongID FROM dbo.Song;

DECLARE @uCount INT = (SELECT COUNT(*) FROM @Users);
DECLARE @sCount INT = (SELECT COUNT(*) FROM @Songs);

;WITH N AS (
    SELECT TOP (500) ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS k
    FROM sys.all_objects
)
INSERT INTO dbo.History (Played_At, UserID, SongID)
SELECT
    DATEADD(MINUTE, -((n.k * 37) % 30240), SYSDATETIME()),   -- ย้อนหลัง ~21 วัน
    u.UserID,
    s.SongID
FROM N AS n
JOIN @Users AS u ON u.rn = 1 + ((n.k * 7) % @uCount)
/* จงใจให้การกระจายเป็น long-tail (เพลงที่ SongID น้อยได้เล่นมากกว่า)
   เพื่อให้หน้า "เพลงยอดนิยม" มีอันดับที่ดูสมจริง ไม่เท่ากันหมด
   POWER(u, 2.2) ไปบีบให้ค่าตกไปทาง index ต่ำ ๆ */
CROSS APPLY (
    SELECT 1 + CAST(POWER((n.k % 100) / 100.0, 2.2) * @sCount AS INT) AS song_rn
) AS w
JOIN @Songs AS s ON s.rn = w.song_rn;
GO

/* ---------------------------------------------------------------------
   ตรวจผลหลัง seed
   --------------------------------------------------------------------- */
PRINT N'--- สรุปจำนวนแถว ---';
SELECT N'ARTIST' AS ตาราง, COUNT(*) AS จำนวน FROM dbo.Artist
UNION ALL SELECT N'ROLE',            COUNT(*) FROM dbo.[Role]
UNION ALL SELECT N'SONG',            COUNT(*) FROM dbo.Song
UNION ALL SELECT N'SONG_ARTIST_ROLE',COUNT(*) FROM dbo.Song_Artist_Role
UNION ALL SELECT N'[USER]',          COUNT(*) FROM dbo.[User]
UNION ALL SELECT N'PLAYLIST',        COUNT(*) FROM dbo.Playlist
UNION ALL SELECT N'PLAYLIST_DETAIL', COUNT(*) FROM dbo.Playlist_Detail
UNION ALL SELECT N'HISTORY',         COUNT(*) FROM dbo.History;

PRINT N'--- 5 เพลงยอดนิยม (PlayCount จาก trigger) ---';
SELECT TOP (5) SongID, SongTitle, PlayCount FROM dbo.Song ORDER BY PlayCount DESC;
GO
