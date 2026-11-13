/* =====================================================================
   Music Streaming Database
   04_email_code.sql : table storing OTP codes for signing in by email

   An extension outside the original ER (added to support email sign-up/sign-in)
   Stores one temporary code per email, valid for 10 minutes (enforced app side)
   ===================================================================== */

USE MusicStreamingDB;
GO
SET NOCOUNT ON;
GO

IF OBJECT_ID(N'dbo.EmailCode', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.EmailCode
    (
        Email      NVARCHAR(255) NOT NULL,
        Code       CHAR(6)       NOT NULL,
        ExpiresAt  DATETIME2(0)  NOT NULL,
        Attempts   INT           NOT NULL CONSTRAINT DF_EmailCode_Attempts DEFAULT (0),
        CreatedAt  DATETIME2(0)  NOT NULL CONSTRAINT DF_EmailCode_CreatedAt DEFAULT (SYSDATETIME()),

        CONSTRAINT PK_EmailCode PRIMARY KEY (Email),
        CONSTRAINT CK_EmailCode_Attempts CHECK (Attempts >= 0)
    );
    PRINT N'สร้างตาราง dbo.EmailCode แล้ว';
END
ELSE
    PRINT N'ตาราง dbo.EmailCode มีอยู่แล้ว';
GO
