# ACI Inventory - Quick Reference Card

## 🎉 Migration Complete!

✅ **364,895 records** migrated successfully
✅ **15 tables** ready to use
✅ **100% success rate**

---

## 🚀 Quick Start Commands

### Start All Services
```bash
cd "/home/tony/ACI Invertory"
docker-compose up -d
```

### Stop All Services
```bash
docker-compose down
```

### View Logs
```bash
docker-compose logs -f web_app
```

---

## 🌐 Access Points

| Service | URL | Credentials |
|---------|-----|-------------|
| **Web App** | http://localhost:5000 | (Application specific) |
| **pgAdmin** | http://localhost:8080 | admin@stockandpick.com / admin123 |
| **PostgreSQL** | localhost:5432 | stockpick_user / stockpick_pass |

---

## 📊 Database Quick Commands

### Connect to Database
```bash
docker-compose exec postgres psql -U stockpick_user -d pcb_inventory
```

### List All Tables
```sql
\dt pcb_inventory.*
```

### Query Examples
```sql
-- View PCB Inventory
SELECT * FROM pcb_inventory."tblPCB_Inventory" LIMIT 10;

-- Count all transactions
SELECT COUNT(*) FROM pcb_inventory."tblTransaction";

-- Get transaction types
SELECT * FROM pcb_inventory."TranCode";

-- Recent receipts
SELECT * FROM pcb_inventory."tblReceipt"
ORDER BY id DESC LIMIT 10;
```

### Exit PostgreSQL
```sql
\q
```

---

## 🗂️ Migrated Tables

| Table | Records | Description |
|-------|---------|-------------|
| tblTransaction | 165,830 | Transaction history |
| tblAVII | 44,269 | AVII data |
| tblPN_List | 33,256 | Part numbers |
| tblReceipt | 32,012 | Receipts |
| tblWhse_Inventory | 31,672 | Warehouse inventory |
| tblPN_list_UPD | 26,298 | Updated part numbers |
| tblBOM | 25,761 | Bill of materials |
| tblLoc | 4,283 | Locations |
| tblPCB_Inventory | 1,034 | PCB inventory |
| tblPN_List_Old | 448 | Old part numbers |
| tblUser | 14 | Users |
| tblPTWY_Entry | 10 | Pathway entries |
| TranCode | 5 | Transaction codes |
| tblCustomerSupply | 2 | Customer supply |
| tblPICK_Entry | 1 | Pick entries |

---

## 💾 Backup & Restore

### Create Backup
```bash
docker-compose exec postgres pg_dump -U stockpick_user pcb_inventory > backup.sql
```

### Restore from Backup
```bash
docker-compose exec -T postgres psql -U stockpick_user pcb_inventory < backup.sql
```

---

## 🔄 Re-run Migration

```bash
cd "/home/tony/ACI Invertory"
./run_migration.sh
```

---

## 📝 Important Notes

1. **Column Names:** Some column names have been transformed for PostgreSQL compatibility
   - Spaces → underscores (`Part Number` → `Part_Number`)
   - Reserved keywords are quoted (`"DESC"`, `"ORDER"`)
   - `ID` column renamed to `original_id` (to avoid conflict with primary key)

2. **Schema:** All tables are in the `pcb_inventory` schema
   - Always use: `pcb_inventory."TableName"`

3. **Table Names:** Case-sensitive and quoted
   - Correct: `"tblPCB_Inventory"`
   - Incorrect: `tblpcb_inventory`

---

## 🔧 Troubleshooting

### PostgreSQL won't start
```bash
docker-compose down
docker-compose up -d postgres
docker-compose logs postgres
```

### Cannot connect to database
```bash
# Check if PostgreSQL is ready
docker-compose exec postgres pg_isready -U stockpick_user
```

### Reset everything
```bash
# WARNING: Deletes all data!
docker-compose down -v
docker-compose up -d
./run_migration.sh
```

---

## 📚 Documentation

- [MIGRATION_COMPLETE.md](MIGRATION_COMPLETE.md) - Full migration report
- [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) - Detailed migration guide
- [migrate_all_tables.py](migrate_all_tables.py) - Migration script source

---

## 🎯 Next Steps

1. ✅ Migration complete
2. ⬜ Start web application: `docker-compose up -d web_app`
3. ⬜ Access app at http://localhost:5000
4. ⬜ Set up automated backups
5. ⬜ Create performance indexes (optional)

---

**Database:** `pcb_inventory`
**Connection:** `postgresql://stockpick_user:stockpick_pass@localhost:5432/pcb_inventory`
**Status:** ✅ Ready to use!
