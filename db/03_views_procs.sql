/* =====================================================================
   Music Streaming Database
   03_views_procs.sql : VIEW (derived attributes) + STORED PROCEDURE
                       + TRIGGER (maintain PlayCount)

   เหตุผลเชิงออกแบบที่อาจารย์มักถาม:
   - Song_Amount / Total_Time เป็น derived attribute => ไม่เก็บซ้ำในตาราง
     แต่คำนวณสด ๆ ด้วย aggregate ใน view (ไม่มีปัญหา update anomaly)
   - PlayCount เป็น stored aggregate ที่ยอมเก็บซ้ำ *โดยเจตนา* เพื่อไม่ต้อง
     COUNT(*) HISTORY ทุกครั้งที่เปิดหน้าแรก -> ใช้ trigger รักษาความถูกต้อง
   ===================================================================== */

USE MusicStreamingDB;
GO
SET NOCOUNT ON;
GO

/* =====================================================================
   VIEW 1 : vw_SongDetail
   รวมเพลง + ศิลปินหลัก + รายชื่อศิลปิน/บทบาททั้งหมดไว้ที่เดียว
   แอปจะเรียก view นี้แทนการ JOIN เองทุกครั้ง
   ===================================================================== */
CREATE OR ALTER VIEW dbo.vw_SongDetail
AS
SELECT
    s.SongID,
    s.SongTitle,
    s.Duration,
    s.PlayCount,
    s.Released_Date,
    ISNULL(main.ArtistID, 0)                AS MainArtistID,
    ISNULL(main.ArtistName, N'ไม่ทราบศิลปิน') AS MainArtistName,
    ISNULL(artists.ArtistList, N'ไม่ทราบศิลปิน') AS ArtistList,
    ISNULL(crew.ArtistRoleList, N'-')       AS ArtistRoleList
FROM dbo.Song AS s
/* ศิลปินหลัก = คนที่บทบาทสำคัญที่สุด (Singer > Featured > อื่น ๆ) */
OUTER APPLY (
    SELECT TOP (1) a.ArtistID, a.ArtistName
    FROM dbo.Song_Artist_Role AS sar
    JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
    JOIN dbo.[Role] AS r ON r.RoleID  = sar.RoleID
    WHERE sar.SongID = s.SongID
    ORDER BY CASE r.[Role] WHEN N'Singer' THEN 0 WHEN N'Featured' THEN 1
                           WHEN N'Composer' THEN 2 ELSE 9 END,
             a.ArtistName
) AS main
/* รายชื่อศิลปินทั้งหมดที่ร่วมร้อง (Singer + Featured) เช่น "PUN, The Toys" */
OUTER APPLY (
    SELECT STRING_AGG(a.ArtistName, N', ') WITHIN GROUP (
               ORDER BY CASE r.[Role] WHEN N'Singer' THEN 0 ELSE 1 END, a.ArtistName) AS ArtistList
    FROM dbo.Song_Artist_Role AS sar
    JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
    JOIN dbo.[Role] AS r ON r.RoleID  = sar.RoleID
    WHERE sar.SongID = s.SongID
      AND r.[Role] IN (N'Singer', N'Featured')
) AS artists
OUTER APPLY (
    SELECT STRING_AGG(CONCAT(a.ArtistName, N' (', r.[Role], N')'), N', ')
           WITHIN GROUP (ORDER BY r.RoleID, a.ArtistName) AS ArtistRoleList
    FROM dbo.Song_Artist_Role AS sar
    JOIN dbo.Artist AS a ON a.ArtistID = sar.ArtistID
    JOIN dbo.[Role] AS r ON r.RoleID  = sar.RoleID
    WHERE sar.SongID = s.SongID
) AS crew;
GO

/* =====================================================================
   VIEW 2 : vw_PlaylistSummary
   = derived attribute Song_Amount + Total_Time ของ ER
   ===================================================================== */
CREATE OR ALTER VIEW dbo.vw_PlaylistSummary
AS
SELECT
    p.PlaylistID,
    p.PLname,
    p.Create_Date,
    p.UserID,
    u.Username,
    COUNT(d.SongID)                             AS Song_Amount,
    ISNULL(SUM(s.Duration), 0)                  AS Total_Time,
    CONCAT(FLOOR(ISNULL(SUM(s.Duration), 0) / 3600), N':',
           RIGHT(CONCAT(N'0', (ISNULL(SUM(s.Duration), 0) % 3600) / 60), 2),
           N':',
           RIGHT(CONCAT(N'0', ISNULL(SUM(s.Duration), 0) % 60), 2))      AS Total_Time_Text
FROM dbo.Playlist AS p
JOIN dbo.[User]   AS u ON u.UserID = p.UserID
LEFT JOIN dbo.Playlist_Detail AS d ON d.PlaylistID = p.PlaylistID
LEFT JOIN dbo.Song            AS s ON s.SongID     = d.SongID
GROUP BY p.PlaylistID, p.PLname, p.Create_Date, p.UserID, u.Username;
GO

/* =====================================================================
   VIEW 3 : vw_PlaylistTrackList
   รายการเพลงในเพลย์ลิสต์ พร้อมลำดับที่แสดงผล (แก้ช่องว่างของ TrackNo
   ที่เกิดจากการลบเพลง ด้วย ROW_NUMBER)
   ===================================================================== */
CREATE OR ALTER VIEW dbo.vw_PlaylistTrackList
AS
SELECT
    d.PlaylistID,
    d.SongID,
    d.TrackNo,
    ROW_NUMBER() OVER (PARTITION BY d.PlaylistID ORDER BY d.TrackNo) AS DisplayNo,
    d.Date_Added,
    vd.SongTitle,
    vd.Duration,
    vd.PlayCount,
    vd.MainArtistID,
    vd.MainArtistName
FROM dbo.Playlist_Detail AS d
JOIN dbo.vw_SongDetail   AS vd ON vd.SongID = d.SongID;
GO

/* =====================================================================
   VIEW 4 : vw_TopSongs
   เพลงยอดนิยม 100 อันดับ (view ไม่รับ parameter จึง fix TOP ไว้)
   ===================================================================== */
CREATE OR ALTER VIEW dbo.vw_TopSongs
AS
SELECT TOP (100)
    vd.SongID, vd.SongTitle, vd.Duration, vd.PlayCount,
    vd.MainArtistID, vd.MainArtistName, vd.Released_Date
FROM dbo.vw_SongDetail AS vd
ORDER BY vd.PlayCount DESC, vd.SongTitle;
GO

/* =====================================================================
   NOTE : trigger trg_History_UpdatePlayCount อยู่ใน 01_schema.sql
          (ย้ายไปอยู่กับ schema เพราะเป็น invariant ของตาราง Song/HISTORY
          และต้องมีอยู่ก่อน 02_seed.sql จะได้บวก PlayCount จากข้อมูลตัวอย่าง)

   PROCEDURE 1 : usp_User_Register
   สมัครสมาชิก + แปลง error ของ UNIQUE ให้เป็นข้อความภาษาไทยที่แอปเอาไปแสดงได้
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_User_Register
    @Username     NVARCHAR(50),
    @Password     NVARCHAR(255),   -- hash ที่คำนวณมาจากฝั่งแอปแล้ว
    @Email        NVARCHAR(255),
    @Gender       NVARCHAR(10)  = NULL,
    @Date_of_Birth DATE         = NULL,
    @Country      NVARCHAR(60)  = NULL,
    @Tel          NVARCHAR(20)  = NULL,
    @NewUserID    INT           = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        INSERT INTO dbo.[User] (Username, Password, Email, Gender, Date_of_Birth, Country, Tel)
        VALUES (@Username, @Password, @Email, @Gender, @Date_of_Birth, @Country, @Tel);

        SET @NewUserID = CAST(SCOPE_IDENTITY() AS INT);
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() IN (2627, 2601)          -- duplicate key
            THROW 50001, N'ชื่อผู้ใช้หรืออีเมลนี้ถูกใช้แล้ว', 1;
        ELSE
            THROW;
    END CATCH
END
GO

/* =====================================================================
   PROCEDURE 2 : usp_Playlist_Create
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_Playlist_Create
    @UserID        INT,
    @PLname        NVARCHAR(120),
    @NewPlaylistID INT = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM dbo.[User] WHERE UserID = @UserID)
        THROW 50010, N'ไม่พบผู้ใช้นี้', 1;

    BEGIN TRY
        INSERT INTO dbo.Playlist (PLname, UserID) VALUES (@PLname, @UserID);
        SET @NewPlaylistID = CAST(SCOPE_IDENTITY() AS INT);
    END TRY
    BEGIN CATCH
        IF ERROR_NUMBER() IN (2627, 2601)
            THROW 50011, N'คุณมีเพลย์ลิสต์ชื่อนี้อยู่แล้ว', 1;
        ELSE
            THROW;
    END CATCH
END
GO

/* =====================================================================
   PROCEDURE 3 : usp_Playlist_AddSong
   ต่อท้ายเพลย์ลิสต์ (TrackNo = MAX + 1) และไม่ error ถ้าเพลงซ้ำอยู่แล้ว
   คืน @Added = 1 (เพิ่มแล้ว) / 0 (มีอยู่แล้ว)
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_Playlist_AddSong
    @PlaylistID INT,
    @SongID     INT,
    @Added      BIT = 0 OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Added = 0;

    IF NOT EXISTS (SELECT 1 FROM dbo.Playlist WHERE PlaylistID = @PlaylistID)
        THROW 50020, N'ไม่พบเพลย์ลิสต์นี้', 1;

    IF NOT EXISTS (SELECT 1 FROM dbo.Song WHERE SongID = @SongID)
        THROW 50021, N'ไม่พบเพลงนี้', 1;

    IF EXISTS (SELECT 1 FROM dbo.Playlist_Detail
               WHERE PlaylistID = @PlaylistID AND SongID = @SongID)
        RETURN;   -- มีเพลงนี้อยู่แล้ว ไม่ทำอะไร

    DECLARE @NextTrackNo INT =
        ISNULL((SELECT MAX(TrackNo) FROM dbo.Playlist_Detail WHERE PlaylistID = @PlaylistID), 0) + 1;

    INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, TrackNo)
    VALUES (@PlaylistID, @SongID, @NextTrackNo);

    SET @Added = 1;
END
GO

/* =====================================================================
   PROCEDURE 4 : usp_Playlist_RemoveSong
   ลบเพลงออกจากเพลย์ลิสต์ (คืน @Removed = 1 ถ้าลบจริง)
   หมายเหตุ: ไม่ re-number TrackNo ที่เหลือ เพราะจะชน UNIQUE index
   ช่องว่างของ TrackNo ถูกกลบด้วย ROW_NUMBER() ใน vw_PlaylistTrackList
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_Playlist_RemoveSong
    @PlaylistID INT,
    @SongID     INT,
    @Removed    BIT = 0 OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    SET @Removed = 0;

    DELETE FROM dbo.Playlist_Detail
    WHERE PlaylistID = @PlaylistID AND SongID = @SongID;

    IF @@ROWCOUNT > 0 SET @Removed = 1;
END
GO

/* =====================================================================
   PROCEDURE 5 : usp_History_Record
   บันทึกการเล่น 1 ครั้ง (PlayCount จะถูกบวกโดย trigger ให้เอง)
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_History_Record
    @UserID INT,
    @SongID INT
AS
BEGIN
    SET NOCOUNT ON;

    IF NOT EXISTS (SELECT 1 FROM dbo.Song WHERE SongID = @SongID)
        THROW 50030, N'ไม่พบเพลงนี้', 1;

    INSERT INTO dbo.History (UserID, SongID) VALUES (@UserID, @SongID);
END
GO

