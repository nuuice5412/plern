/* =====================================================================
   Music Streaming Database
   03_views_procs.sql : VIEW (derived attributes) + STORED PROCEDURE
                       + TRIGGER (maintain PlayCount)

   Design rationale examiners often ask about:
   - Song_Amount / Total_Time are derived attributes => not duplicated in tables
     but computed live with aggregates in the view (no update anomaly issues)
   - PlayCount is a stored aggregate we duplicate *on purpose* so we do not
     COUNT(*) HISTORY on every home page load -> a trigger keeps it correct
   ===================================================================== */

USE MusicStreamingDB;
GO
SET NOCOUNT ON;
GO

/* =====================================================================
   VIEW 1 : vw_SongDetail
   Combines songs + main artist + full artist/role list in one place
   The app calls this view instead of hand-writing JOINs every time
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
/* Main artist = the one with the most important role (Singer > Featured > others) */
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
/* All artists who performed vocals (Singer + Featured), e.g. "PUN, The Toys" */
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
   = the ER's derived attributes Song_Amount + Total_Time
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
   Songs in a playlist with a display sequence (fills the TrackNo gaps
   left by deleted songs using ROW_NUMBER)
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
   Top 100 popular songs (views take no parameters, so TOP is fixed)
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
   NOTE : trigger trg_History_UpdatePlayCount lives in 01_schema.sql
          (moved next to the schema because it is an invariant of the Song/HISTORY tables
          and must exist before 02_seed.sql so sample data can add to PlayCount)

   PROCEDURE 1 : usp_User_Register
   Register a user + turn UNIQUE errors into displayable messages for the app
   ===================================================================== */
CREATE OR ALTER PROCEDURE dbo.usp_User_Register
    @Username     NVARCHAR(50),
    @Password     NVARCHAR(255),   -- hash already computed on the app side
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
   Append to the end of a playlist (TrackNo = MAX + 1); no error if the song is already there
   Returns @Added = 1 (added) / 0 (already present)
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
        RETURN;   -- song already present, do nothing

    DECLARE @NextTrackNo INT =
        ISNULL((SELECT MAX(TrackNo) FROM dbo.Playlist_Detail WHERE PlaylistID = @PlaylistID), 0) + 1;

    INSERT INTO dbo.Playlist_Detail (PlaylistID, SongID, TrackNo)
    VALUES (@PlaylistID, @SongID, @NextTrackNo);

    SET @Added = 1;
END
GO

/* =====================================================================
   PROCEDURE 4 : usp_Playlist_RemoveSong
   Remove a song from a playlist (returns @Removed = 1 if something was deleted)
   Note: remaining TrackNo values are not re-numbered because that would hit the UNIQUE index
   TrackNo gaps are masked by ROW_NUMBER() in vw_PlaylistTrackList
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
   Record one play (the trigger adds to PlayCount on its own)
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

