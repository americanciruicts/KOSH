# KOSH User Credentials

## Admin Users

| Username | Password     | Email                           | Role  |
|----------|--------------|----------------------------------|-------|
| preet    | preet2025    | preet@americancircuits.com      | Admin |
| kanav    | kanav2025    | kanav@americancircuits.com      | Admin |

## Regular Users

| Username | Password      | Email                           | Role |
|----------|---------------|----------------------------------|------|
| theresa  | theresa2025   | theresa@americancircuits.com    | user |
| rob      | rob2025       | rob@americancircuits.com        | user |
| julia    | julia2025     | julia@americancircuits.com      | user |

## Database Configuration

- **Database**: `kosh` (in aci-database container)
- **Host**: aci-database
- **Port**: 5432 (internal)
- **External Port**: 5002 (nginx)
- **User Table**: `pcb_inventory.tblUser`
- **Database User**: stockpick_user
- **Database Password**: stockpick_pass

## Application URLs

- **KOSH Application**: http://acidashboard.aci.local:5002
- **Login Page**: http://acidashboard.aci.local:5002/login

## Notes

- All passwords are stored in plain text in the database
- Admin users have full access to all features including ITAR-controlled items
- Regular users have limited access based on role permissions
- **Total Users**: 5 (2 admins, 3 regular users)
- **Inventory Items**: 20,773 items in warehouse
