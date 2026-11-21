# แนวทางพรีเซนต์ (อิงจากตัวอย่างรายงาน SmartParking ที่อาจารย์ให้มา)

## สรุปสิ่งที่อาจารย์ต้องการ

ตัวอย่างรายงานของรุ่นพี่แบ่งการสาธิตเป็น 5 ขั้น ตามที่เขียนด้วยมือในเล่ม:

| ลำดับ | ขั้น | สาธิตอะไร |
|---|---|---|
| 1 | **Connect** | เชื่อมต่อฐานข้อมูล |
| 2 | **Select** | ดึงข้อมูลมาแสดงที่ frontend |
| 3 | **Insert** | เพิ่มข้อมูลลงตาราง |
| 4 | **Update** | แก้ไขค่าของแถว |
| 5 | **Delete** | ลบข้อมูล |

> ที่คุณลืมคือ **SELECT** — และเขามี **Connect** นำหน้าด้วย

---

## วิธีสาธิตของ Plern (2 ทาง เลือกได้)

### ทาง A — รันสคริปต์ให้เห็น SQL จริง (แนะนำ)

```powershell
cd C:\Users\IMOS\Documents\Spi
.\.venv\Scripts\python.exe tools\demo_crud.py --pause
```

`--pause` จะหยุดรอ Enter ทีละขั้น เหมาะกับการพรีเซนต์

สคริปต์จะพิมพ์ SQL จริง + ผลลัพธ์ทีละขั้น:

```
1) CONNECT   DBMS / Database / Server / User / จำนวนตาราง
2) SELECT    SELECT ... JOIN 4 ตาราง  → ตารางผลลัพธ์ 5 แถว
             + อ่านผ่าน VIEW vw_PlaylistSummary
3) INSERT    INSERT INTO Playlist ... OUTPUT INSERTED.PlaylistID
             INSERT INTO Playlist_Detail ...
4) UPDATE    UPDATE dbo.Playlist SET PLname = ? WHERE PlaylistID = ?
             (แสดงชื่อก่อน/หลัง + rowcount)
5) DELETE    DELETE FROM Playlist_Detail / DELETE FROM Playlist
             (ตรวจว่าเหลือ 0 แถว)

โบนัส: TRIGGER · STORED PROCEDURE (OUTPUT param) · TRANSACTION + ROLLBACK
```

ตอนจบจะ **ROLLBACK ทั้งหมด** — ฐานข้อมูลไม่เปื้อน ถ้าอยากให้ผลค้างไว้ใช้ `--keep`

### ทาง B — กดในเว็บจริง

| ขั้น | ไปที่ | ทำอะไร |
|---|---|---|
| **Select** | `/songs` · `/artists` · `/` | เปิดดูข้อมูลที่ดึงจาก DB |
| **Insert** | `/playlists` → สร้างเพลย์ลิสต์ | `INSERT INTO Playlist` |
| | หน้าเพลง → เพิ่มเข้าเพลย์ลิสต์ | `INSERT INTO Playlist_Detail` |
| | กดเล่นเพลง | `INSERT INTO History` (trigger บวก PlayCount) |
| **Update** | ตั้งค่า → บัญชี → จัดการ | `UPDATE dbo.[User] SET ...` |
| | ตั้งค่า → รหัสผ่าน | `UPDATE dbo.[User] SET Password` |
| **Delete** | เพลย์ลิสต์ → ลบเพลง | `DELETE FROM Playlist_Detail` |
| | เพลย์ลิสต์ → ลบเพลย์ลิสต์ | `DELETE FROM Playlist` |

---

## สิ่งที่ควรพูดตอนพรีเซนต์ (สั้น ๆ ต่อขั้น)

**Connect**
> "แอปเชื่อม SQL Server ผ่าน pyodbc โดยใช้ connection string จาก environment variable
> ไม่ได้ hardcode รหัสผ่านไว้ในโค้ด"

**Select**
> "ทุกหน้าไม่มีข้อมูลฝังในโค้ด ทุกค่ามาจาก query จริง
> หน้านี้ join 4 ตาราง (Song, Artist, Song_Artist_Role, Role) เพื่อแยกว่าใครร้องเพลงนี้"

**Insert**
> "ผู้ใช้สร้างเพลย์ลิสต์ → INSERT 2 ตาราง (Playlist และ Playlist_Detail)
> ใน transaction เดียว ถ้าพลาดกลางทางจะ rollback"

**Update**
> "แก้ข้อมูลบัญชี → UPDATE เฉพาะคอลัมน์ที่ส่งมา และตรวจชื่อซ้ำก่อนเขียน"

**Delete**
> "ลบเพลย์ลิสต์ → ลบรายละเอียดก่อนแล้วลบหัว ตารางมี FK ON DELETE CASCADE
> แต่เราเลือก explicit delete เพื่อให้เห็นลำดับ"

---

## โบนัสที่ทำให้เหนือกว่ารุ่นพี่ (พูดเพิ่มได้ 30 วินาที)

| ของ | อยู่ตรงไหน | พูดว่า |
|---|---|---|
| **Trigger** | `trg_History_UpdatePlayCount` | "ยอดฟังเพิ่มเองเมื่อ INSERT History — ไม่มี UPDATE ในโค้ดแอป" |
| **View** | 4 views | "หน้าเพลย์ลิสต์อ่านจาก `vw_PlaylistSummary` ที่คำนวณจำนวนเพลง/ความยาวให้" |
| **Stored Procedure** | 5 procs | "สร้างเพลย์ลิสต์เรียก `usp_Playlist_Create` ที่มี OUTPUT parameter คืนรหัสใหม่" |
| **Transaction** | หลาย route | "INSERT หลายตารางอยู่ใน transaction เดียว" |
| **Security** | `app/auth.py` | "รหัสผ่านเก็บเป็น PBKDF2-SHA256 ไม่เก็บ plain text" |

---

## แบ่งหน้าที่ (ถ้าเป็นงานกลุ่ม)

ตัวอย่างของรุ่นพี่แบ่งคนละส่วน (Connect / Insert / Select / Update / Delete)

| คน | รับผิดชอบ |
|---|---|
| 1 | Connect + Select |
| 2 | Insert |
| 3 | Update |
| 4 | Delete |
| 5 | Trigger/View/Procedure + สรุป |

---

## เช็คก่อนขึ้นพรีเซนต์

```
□ รัน python run.py ไว้ก่อน (มีคนเปิดเว็บอยู่)
□ เปิด tools/demo_crud.py --pause ไว้ใน terminal อีกหน้าต่าง
□ ฐานข้อมูลสำรองแล้ว (tools/backup_db.py)
□ เปิด /songs และ /playlists ไว้ในแท็บสำรอง
□ ถ้าเน็ตพัง — สคริปต์ demo_crud.py ทำงานได้โดยไม่ต้องใช้เน็ต
```
