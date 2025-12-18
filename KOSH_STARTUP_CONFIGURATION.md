# KOSH (Stock and Pick) Startup Configuration

## Issues Fixed

### 1. Containers Not Starting on Boot
- **Problem**: Containers had `restart: unless-stopped` policy and RestartPolicy was not applied
- **Solution**: Changed to `restart: always` and recreated containers
- **Status**: ✅ Fixed - Both containers now have automatic restart enabled

### 2. Database Conflict
- **Problem**: Docker-compose was trying to create a duplicate `aci-database` container
- **Solution**: Commented out postgres service and configured web_app to use the existing external database
- **Status**: ✅ Fixed - Using shared database container

### 3. Database Connection
- **Problem**: Web app was configured to connect to `postgres` hostname
- **Solution**: Updated connection to use `aci-database` hostname
- **Status**: ✅ Fixed - Application connects to correct database

## Automatic Startup Configuration

### Docker Containers
All KOSH containers are configured to start automatically on system boot:
- `restart: always` policy is set for all containers
- Containers will start when Docker service starts
- No manual intervention required after reboot

### Verified Containers with Auto-Restart:
- ✅ stockandpick_webapp (Flask application) - Status: healthy
- ✅ stockandpick_nginx (Reverse proxy) - Status: running
- ✅ aci-database (Shared PostgreSQL) - Status: healthy

### Current Status:
```
stockandpick_nginx     Up and running         Port: 5002->80
stockandpick_webapp    Up and healthy         Port: 5000 (internal)
aci-database          Up and healthy         Port: 5434->5432
```

## Windows Client Configuration

To access the KOSH application from Windows machines, add this entry to your Windows hosts file:

### Steps:
1. Open Notepad as Administrator
2. Open file: `C:\Windows\System32\drivers\etc\hosts`
3. Add this line at the end:
   ```
   192.168.1.95  acidashboard.aci.local
   ```

4. Save the file
5. Access KOSH at: **http://acidashboard.aci.local:5002**

### Current Server IP:
- **Server IP**: 192.168.1.95
- **KOSH Port**: 5002
- **ACI Dashboard Port**: 2005

## Application URLs

From Windows machines (after adding hosts file entry):
- **KOSH Stock & Pick**: http://acidashboard.aci.local:5002
- **ACI Dashboard**: http://acidashboard.aci.local:2005

From the server itself:
- **KOSH Stock & Pick**: http://localhost:5002
- **ACI Dashboard**: http://localhost:2005

## Verification Commands

### Check KOSH containers are running:
```bash
docker ps --filter "name=stockandpick" --format "table {{.Names}}\t{{.Status}}"
```

### Check restart policies:
```bash
docker inspect stockandpick_webapp stockandpick_nginx --format='{{.Name}}: RestartPolicy={{.HostConfig.RestartPolicy.Name}}'
```

### View KOSH web app logs:
```bash
docker logs stockandpick_webapp --tail 50
```

### View KOSH nginx logs:
```bash
docker logs stockandpick_nginx --tail 50
```

### Test KOSH accessibility:
```bash
curl -I http://localhost:5002
```

### Restart KOSH services if needed:
```bash
cd "/home/tony/ACI Invertory"
docker-compose restart
```

## Why It Should Work Every Morning Now

1. **Docker Auto-Start**: Docker service starts automatically on system boot
2. **Container Auto-Restart**: All containers have `restart: always` policy
3. **Shared Database**: Uses the same PostgreSQL database as other applications
4. **No Dependencies**: Removed service dependencies that could cause startup issues
5. **Fixed Configuration**: All paths and hostnames are correct

The KOSH application will be available within 30 seconds after system boot, giving time for:
- Docker service to start
- Database to be ready
- Web application to initialize
- Nginx to start accepting connections

## Database Configuration

### Shared Database Details:
- **Container**: aci-database
- **Database**: pcb_inventory
- **User**: stockpick_user
- **Port**: 5434 (external), 5432 (internal)
- **Connection**: postgresql://stockpick_user:stockpick_pass@aci-database:5432/pcb_inventory

The KOSH application shares the PostgreSQL database with:
- ACI Dashboard
- Other inventory management tools

## Troubleshooting

If KOSH is not accessible after boot:

1. **Check if containers are running:**
   ```bash
   docker ps -a --filter "name=stockandpick"
   ```

2. **Check container logs for errors:**
   ```bash
   docker logs stockandpick_webapp --tail 100
   docker logs stockandpick_nginx --tail 50
   ```

3. **Check database connectivity:**
   ```bash
   docker exec stockandpick_webapp python -c "import psycopg2; conn = psycopg2.connect('postgresql://stockpick_user:stockpick_pass@aci-database:5432/pcb_inventory'); print('Connected!'); conn.close()"
   ```

4. **Check if port 5002 is accessible:**
   ```bash
   curl http://localhost:5002
   ```

5. **Restart containers manually:**
   ```bash
   cd "/home/tony/ACI Invertory"
   docker-compose restart
   ```

6. **View docker-compose status:**
   ```bash
   cd "/home/tony/ACI Invertory"
   docker-compose ps
   ```

## Network Configuration

### Container Networks:
- **Network**: stockpick-network (bridge)
- **External Link**: aci-database (shared with other applications)

### Port Mapping:
- 5002:80 (nginx - external access)
- 5000 (webapp - internal only)

## Configuration Changes Made

1. **Updated docker-compose.yml**:
   - Commented out postgres service (using external database)
   - Changed restart policy from `unless-stopped` to `always`
   - Updated POSTGRES_HOST to `aci-database`
   - Added external_links for database connectivity

2. **Recreated containers**:
   - Removed old containers
   - Created new containers with updated configuration
   - Verified restart policies are applied

## Additional Notes

- The KOSH application is now using the same database instance as other applications
- All containers will start automatically on system reboot
- No manual intervention is required
- The application is accessible from both local server and Windows clients
- Health checks are passing successfully
