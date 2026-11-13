/* =====================================================================
   Music Streaming Database
   04_email_code.sql : ตารางเก็บรหัส OTP สำหรับเข้าสู่ระบบด้วยอีเมล

   เป็นส่วนขยายนอก ER เดิม (เพิ่มเพื่อรองรับการสมัคร/ล็อกอินด้วยอีเมล)
   เก็บรหัสชั่วคราว 1 รหัสต่ออีเมล อายุ 10 นาที (กำหนดที่ฝั่งแอป)
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
