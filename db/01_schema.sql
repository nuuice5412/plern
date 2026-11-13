/* =====================================================================
   Music Streaming Database
   01_schema.sql : create the database + all tables + constraints + indexes + triggers

   Structure follows the group's ER Diagram (Peter Chen):
     USER 1---N PLAYLIST 1---N PLAYLIST_DETAIL N---1 SONG
     USER 1---N HISTORY  N---1 SONG
     SONG M---N ARTIST  (via SONG_ARTIST_ROLE with ROLE as the link)

   Notes:
   - [User] and [Role] are T-SQL reserved words, so always wrap them in [ ]
   - Song_Amount / Total_Time in the ER are derived attributes (dashed oval)
     so they are not stored as columns but computed in vw_PlaylistSummary (see 03_views_procs.sql)
   - PlayCount is updated automatically by a trigger when a new row lands in HISTORY
   This script is re-runnable (drop then recreate), good for development/submission
   ===================================================================== */

SET NOCOUNT ON;
GO

IF DB_ID(N'MusicStreamingDB') IS NULL
BEGIN
    CREATE DATABASE MusicStreamingDB;
END
GO

USE MusicStreamingDB;
GO

/* ---------------------------------------------------------------------
   0) Drop existing objects (order must reverse creation because of FKs)
   --------------------------------------------------------------------- */
IF OBJECT_ID(N'dbo.trg_History_UpdatePlayCount', N'TR') IS NOT NULL
    DROP TRIGGER dbo.trg_History_UpdatePlayCount;
GO
IF OBJECT_ID(N'dbo.usp_History_Record', N'P') IS NOT NULL DROP PROCEDURE dbo.usp_History_Record;
IF OBJECT_ID(N'dbo.usp_Playlist_RemoveSong', N'P') IS NOT NULL DROP PROCEDURE dbo.usp_Playlist_RemoveSong;
IF OBJECT_ID(N'dbo.usp_Playlist_AddSong', N'P') IS NOT NULL DROP PROCEDURE dbo.usp_Playlist_AddSong;
IF OBJECT_ID(N'dbo.usp_Playlist_Create', N'P') IS NOT NULL DROP PROCEDURE dbo.usp_Playlist_Create;
IF OBJECT_ID(N'dbo.usp_User_Register', N'P') IS NOT NULL DROP PROCEDURE dbo.usp_User_Register;
GO
IF OBJECT_ID(N'dbo.vw_TopSongs', N'V') IS NOT NULL DROP VIEW dbo.vw_TopSongs;
IF OBJECT_ID(N'dbo.vw_PlaylistTrackList', N'V') IS NOT NULL DROP VIEW dbo.vw_PlaylistTrackList;
IF OBJECT_ID(N'dbo.vw_PlaylistSummary', N'V') IS NOT NULL DROP VIEW dbo.vw_PlaylistSummary;
IF OBJECT_ID(N'dbo.vw_SongDetail', N'V') IS NOT NULL DROP VIEW dbo.vw_SongDetail;
GO
IF OBJECT_ID(N'dbo.Song_Artist_Role', N'U') IS NOT NULL DROP TABLE dbo.Song_Artist_Role;
IF OBJECT_ID(N'dbo.Playlist_Detail', N'U') IS NOT NULL DROP TABLE dbo.Playlist_Detail;
IF OBJECT_ID(N'dbo.History', N'U') IS NOT NULL DROP TABLE dbo.History;
IF OBJECT_ID(N'dbo.Playlist', N'U') IS NOT NULL DROP TABLE dbo.Playlist;
IF OBJECT_ID(N'dbo.Song', N'U') IS NOT NULL DROP TABLE dbo.Song;
IF OBJECT_ID(N'dbo.Artist', N'U') IS NOT NULL DROP TABLE dbo.Artist;
IF OBJECT_ID(N'dbo.[Role]', N'U') IS NOT NULL DROP TABLE dbo.[Role];
IF OBJECT_ID(N'dbo.[User]', N'U') IS NOT NULL DROP TABLE dbo.[User];
GO

/* =====================================================================
   1) [User]
      ER: UserID, Username, Password, Email, Gender, Date_of_Birth,
          Country, Tel
      Password is stored as a hash string in the form
          pbkdf2_sha256$<iterations>$<salt hex>$<hash hex>
      (no plaintext stored — even though the column name matches the ER)
   ===================================================================== */
CREATE TABLE dbo.[User]
(
    UserID          INT IDENTITY(1,1) NOT NULL,
    Username        NVARCHAR(50)      NOT NULL,
    Password        NVARCHAR(255)     NOT NULL,
    Email           NVARCHAR(255)     NOT NULL,
    Gender          NVARCHAR(10)      NULL,
    Date_of_Birth   DATE              NULL,
    Country         NVARCHAR(60)      NULL,
    Tel             NVARCHAR(20)      NULL,

    CONSTRAINT PK_User PRIMARY KEY (UserID),
    CONSTRAINT UQ_User_Username UNIQUE (Username),
    CONSTRAINT UQ_User_Email UNIQUE (Email),
    CONSTRAINT CK_User_Gender CHECK (Gender IS NULL OR Gender IN (N'Male', N'Female', N'Other')),
    CONSTRAINT CK_User_Email CHECK (Email LIKE N'%_@_%._%')
);
GO

/* =====================================================================
   2) ARTIST
      ER: ArtistID, ArtistName, Country, Bio
   ===================================================================== */
CREATE TABLE dbo.Artist
(
    ArtistID    INT IDENTITY(1,1) NOT NULL,
    ArtistName  NVARCHAR(150)     NOT NULL,
    Country     NVARCHAR(60)      NULL,
    Bio         NVARCHAR(1000)    NULL,

    CONSTRAINT PK_Artist PRIMARY KEY (ArtistID),
    CONSTRAINT UQ_Artist_ArtistName UNIQUE (ArtistName)
);
GO

/* =====================================================================
   3) [Role]  — an artist's role on a given song
      ER: RoleID, Role, Role_desc
   ===================================================================== */
CREATE TABLE dbo.[Role]
(
    RoleID     INT IDENTITY(1,1) NOT NULL,
    [Role]     NVARCHAR(50)      NOT NULL,
    Role_desc  NVARCHAR(300)     NULL,

    CONSTRAINT PK_Role PRIMARY KEY (RoleID),
    CONSTRAINT UQ_Role_Role UNIQUE ([Role])
);
GO

/* =====================================================================
   4) SONG
      ER: SongID, SongTitle, Duration, PlayCount, Released_Date
      Duration = length in seconds
      PlayCount = counter (denormalized for speed) maintained by a trigger
   ===================================================================== */
CREATE TABLE dbo.Song
(
    SongID         INT IDENTITY(1,1) NOT NULL,
    SongTitle      NVARCHAR(200)     NOT NULL,
    Duration       INT               NOT NULL,
    PlayCount      INT               NOT NULL CONSTRAINT DF_Song_PlayCount DEFAULT (0),
    Released_Date  DATE              NULL,

    CONSTRAINT PK_Song PRIMARY KEY (SongID),
    CONSTRAINT CK_Song_Duration CHECK (Duration BETWEEN 1 AND 7200),
    CONSTRAINT CK_Song_PlayCount CHECK (PlayCount >= 0)
);
GO

/* =====================================================================
   5) PLAYLIST
      ER: PlaylistID, PLname, Create_Date, UserID(FK)
      One playlist belongs to one USER (1..N), hence NOT NULL
   ===================================================================== */
CREATE TABLE dbo.Playlist
(
    PlaylistID   INT IDENTITY(1,1) NOT NULL,
    PLname       NVARCHAR(120)     NOT NULL,
    Create_Date  DATETIME2(0)      NOT NULL CONSTRAINT DF_Playlist_Create_Date DEFAULT (SYSDATETIME()),
    UserID       INT               NOT NULL,

    CONSTRAINT PK_Playlist PRIMARY KEY (PlaylistID),
    CONSTRAINT UQ_Playlist_User_Name UNIQUE (UserID, PLname),
    CONSTRAINT FK_Playlist_User FOREIGN KEY (UserID)
        REFERENCES dbo.[User] (UserID) ON DELETE CASCADE
);
GO

/* =====================================================================
   6) PLAYLIST_DETAIL  — junction table for PLAYLIST M---N SONG
      ER: PlaylistID(FK), SongID(FK), Date_Added, TrackNo
      Composite PK (PlaylistID, SongID) => the same song cannot repeat in one playlist
   ===================================================================== */
CREATE TABLE dbo.Playlist_Detail
(
    PlaylistID  INT           NOT NULL,
    SongID      INT           NOT NULL,
    Date_Added  DATETIME2(0)  NOT NULL CONSTRAINT DF_Playlist_Detail_Date_Added DEFAULT (SYSDATETIME()),
    TrackNo     INT           NOT NULL,

    CONSTRAINT PK_Playlist_Detail PRIMARY KEY (PlaylistID, SongID),
    CONSTRAINT FK_Playlist_Detail_Playlist FOREIGN KEY (PlaylistID)
        REFERENCES dbo.Playlist (PlaylistID) ON DELETE CASCADE,
    CONSTRAINT FK_Playlist_Detail_Song FOREIGN KEY (SongID)
        REFERENCES dbo.Song (SongID),
    CONSTRAINT CK_Playlist_Detail_TrackNo CHECK (TrackNo > 0)
);
GO

/* Track numbers within a playlist must be unique */
CREATE UNIQUE INDEX UQ_Playlist_Detail_TrackNo
    ON dbo.Playlist_Detail (PlaylistID, TrackNo);
GO

/* =====================================================================
   7) HISTORY  — playback history (fact table for analytics)
      ER: HistoryID, Played_At, UserID(FK), SongID(FK)
   ===================================================================== */
CREATE TABLE dbo.History
(
    HistoryID  BIGINT IDENTITY(1,1) NOT NULL,
    Played_At  DATETIME2(0)         NOT NULL CONSTRAINT DF_History_Played_At DEFAULT (SYSDATETIME()),
    UserID     INT                  NOT NULL,
    SongID     INT                  NOT NULL,

    CONSTRAINT PK_History PRIMARY KEY (HistoryID),
    CONSTRAINT FK_History_User FOREIGN KEY (UserID)
        REFERENCES dbo.[User] (UserID),
    CONSTRAINT FK_History_Song FOREIGN KEY (SongID)
        REFERENCES dbo.Song (SongID)
);
GO

/* =====================================================================
   8) SONG_ARTIST_ROLE  — ternary relationship SONG M---N ARTIST (via ROLE)
      ER: SongID(FK), ArtistID(FK), RoleID(FK)
      "Artist X does job Y on song Z"  e.g. Nova Lane is Singer on Paper Lanterns
   ===================================================================== */
CREATE TABLE dbo.Song_Artist_Role
(
    SongID    INT NOT NULL,
    ArtistID  INT NOT NULL,
    RoleID    INT NOT NULL,

    CONSTRAINT PK_Song_Artist_Role PRIMARY KEY (SongID, ArtistID, RoleID),
    CONSTRAINT FK_SAR_Song FOREIGN KEY (SongID)
        REFERENCES dbo.Song (SongID) ON DELETE CASCADE,
    CONSTRAINT FK_SAR_Artist FOREIGN KEY (ArtistID)
        REFERENCES dbo.Artist (ArtistID),
    CONSTRAINT FK_SAR_Role FOREIGN KEY (RoleID)
        REFERENCES dbo.[Role] (RoleID)
);
GO

/* ---------------------------------------------------------------------
   9) TRIGGER : keep Song.PlayCount in sync with HISTORY

      Why not COUNT(*) every time: the app's home page ranks popular songs
      COUNT(*) over HISTORY (which keeps growing) on every page load would be slow
      so we store PlayCount redundantly (denormalize) and use a trigger to keep it correct
      Written set-based (GROUP BY inserted) to handle multi-row inserts
   --------------------------------------------------------------------- */
CREATE TRIGGER dbo.trg_History_UpdatePlayCount
ON dbo.History
AFTER INSERT
AS
BEGIN
    SET NOCOUNT ON;

    UPDATE s
       SET s.PlayCount = s.PlayCount + x.cnt
    FROM dbo.Song AS s
    JOIN (SELECT SongID, COUNT(*) AS cnt FROM inserted GROUP BY SongID) AS x
      ON x.SongID = s.SongID;
END
GO

/* ---------------------------------------------------------------------
   10) Extra indexes for queries the app runs often
       (FKs do not get indexes automatically in SQL Server)
   --------------------------------------------------------------------- */
CREATE INDEX IX_History_User_PlayedAt ON dbo.History (UserID, Played_At DESC) INCLUDE (SongID);
CREATE INDEX IX_History_Song          ON dbo.History (SongID);
CREATE INDEX IX_Playlist_User         ON dbo.Playlist (UserID);
CREATE INDEX IX_Playlist_Detail_Song  ON dbo.Playlist_Detail (SongID);
CREATE INDEX IX_SAR_Artist_Role       ON dbo.Song_Artist_Role (ArtistID, RoleID);
CREATE INDEX IX_Song_PlayCount        ON dbo.Song (PlayCount DESC) INCLUDE (SongTitle);
GO
