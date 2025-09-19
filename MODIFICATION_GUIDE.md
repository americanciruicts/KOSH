# MODIFICATION GUIDE - Stock and Pick PCB Inventory System
## Quick Reference for Future Development

---

## 🎯 CURRENT SYSTEM OVERVIEW

**Status**: Production-ready Flask web application with PostgreSQL backend  
**Location**: `/Users/khashsarrafi/Projects/revestData/migration/stockAndPick/`  
**Access**: http://localhost:5002 (web app), localhost:5432 (database)

---

## 🚀 QUICK START FOR MODIFICATIONS

### **1. Start Development Environment**
```bash
cd /Users/khashsarrafi/Projects/revestData/migration/stockAndPick
docker-compose up -d
# Verify: curl http://localhost:5002/health
```

### **2. Make Code Changes**
- **Flask Routes**: Edit `web_app/app.py` (lines 264+)
- **Templates**: Modify files in `web_app/templates/`  
- **Database**: Update schema in `init/01-create-schema.sql`
- **Styles**: Bootstrap 5 classes in templates

### **3. Apply Changes**
```bash
# Rebuild and restart
docker-compose build web_app
docker-compose up -d
# Test: curl http://localhost:5002/health
```

---

## 📁 KEY FILES TO MODIFY

### **Main Application Logic**
- **`web_app/app.py`** (392 lines)
  - Lines 88-94: Form definitions
  - Lines 264-400: Route handlers
  - Lines 28-56: Template filters and context processors

### **User Interface**
- **`web_app/templates/base.html`** - Main layout and navigation
- **`web_app/templates/index.html`** - Dashboard page
- **`web_app/templates/stock.html`** - Add inventory form
- **`web_app/templates/pick.html`** - Remove inventory form
- **`web_app/templates/inventory.html`** - Search/browse page
- **`web_app/templates/reports.html`** - Analytics page

### **Configuration**
- **`docker-compose.yml`** - Service configuration (ports, environment)
- **`web_app/requirements.txt`** - Python dependencies
- **`web_app/Dockerfile`** - Container build instructions

---

## 🔧 COMMON MODIFICATION PATTERNS

### **Adding a New Page**

1. **Create Route** in `app.py`:
```python
@app.route('/new-page')
def new_page():
    return render_template('new-page.html', data=some_data)
```

2. **Create Template** `web_app/templates/new-page.html`:
```html
{% extends "base.html" %}
{% block content %}
<h1>New Page Content</h1>
{% endblock %}
```

3. **Add Navigation** in `base.html`:
```html
<a class="nav-link" href="{{ url_for('new_page') }}">New Page</a>
```

### **Adding Database Fields**

1. **Update Schema** in `init/01-create-schema.sql`:
```sql
ALTER TABLE pcb_inventory.tblpcb_inventory 
ADD COLUMN new_field VARCHAR(100);
```

2. **Update Forms** in `app.py`:
```python
class StockForm(FlaskForm):
    new_field = StringField('New Field', validators=[DataRequired()])
```

3. **Update Templates** to include new field in forms and displays

### **Adding API Endpoints**

1. **Add Route** in `app.py`:
```python
@app.route('/api/new-endpoint')
def api_new_endpoint():
    return jsonify({'success': True, 'data': data})
```

2. **Update JavaScript** in templates to call new endpoint:
```javascript
fetch('/api/new-endpoint')
    .then(response => response.json())
    .then(data => console.log(data));
```

---

## 🧪 TESTING MODIFICATIONS

### **Quick Validation**
```bash
# 1. Check containers are healthy
docker-compose ps

# 2. Test web app responds
curl -s http://localhost:5002/health

# 3. Check for JavaScript errors
# Open browser dev tools at http://localhost:5002

# 4. Test database connection
docker-compose exec postgres psql -U stockpick_user -d pcb_inventory -c "SELECT COUNT(*) FROM pcb_inventory.tblpcb_inventory;"

# 5. Check logs for errors
docker-compose logs web_app --tail 20
```

### **Functional Testing Checklist**
- [ ] Dashboard loads with real data
- [ ] Stock form accepts and validates input
- [ ] Pick form shows confirmation modal
- [ ] Inventory search returns results
- [ ] Reports page displays analytics
- [ ] All API endpoints return JSON
- [ ] No JavaScript console errors
- [ ] Database operations work correctly

---

## 📊 CURRENT DATA STATE

### **Database Content**
- **25 inventory records** with real job numbers
- **15 unique jobs**: 77890, 8034, 7143, 8328, 7703, etc.
- **4,240 total PCB quantity** across all items
- **PCB Types**: Bare, Partial, Completed, Ready to Ship
- **Locations**: 1000-1999 through 10000-10999 ranges

### **Sample Data Query**
```sql
-- View current inventory
SELECT job, pcb_type, qty, location 
FROM pcb_inventory.tblpcb_inventory 
ORDER BY job, pcb_type;

-- Check audit trail
SELECT * FROM pcb_inventory.inventory_audit 
ORDER BY timestamp DESC LIMIT 10;
```

---

## 🔍 TROUBLESHOOTING MODIFICATIONS

### **Common Issues & Solutions**

#### **Container Won't Start**
```bash
# Check logs
docker-compose logs web_app

# Common fixes:
# 1. Syntax error in app.py - check Python syntax
# 2. Missing dependency - update requirements.txt
# 3. Port conflict - change port in docker-compose.yml
```

#### **Database Connection Error**
```bash
# Verify PostgreSQL is running
docker-compose ps postgres

# Check database exists
docker-compose exec postgres psql -U stockpick_user -l

# Recreate database if needed
docker-compose down
docker volume rm stockandpick_postgres_data
docker-compose up -d postgres
python3 simple_migration.py  # Re-migrate data
```

#### **Template Errors**
```bash
# Check Jinja2 syntax in templates
# Common issues:
# 1. Missing {% endblock %} tags
# 2. Undefined variables in {{ }} expressions
# 3. Missing template inheritance {% extends "base.html" %}
```

#### **JavaScript Errors**
```bash
# Check browser console for errors
# Common issues:
# 1. Missing element IDs referenced in JavaScript
# 2. Form submission conflicts (use HTMLFormElement.prototype.submit.call())
# 3. Missing null checks for DOM elements
```

---

## 🔧 DEVELOPMENT BEST PRACTICES

### **Code Organization**
- Keep routes in `app.py` organized by functionality
- Use consistent naming conventions for templates
- Add comments for complex business logic
- Follow Flask best practices for forms and validation

### **Database Changes**
- Always backup before schema changes: `docker-compose exec postgres pg_dump -U stockpick_user pcb_inventory > backup.sql`
- Test schema changes in development first
- Update migration scripts for reproducibility

### **Container Management**
- Use `docker-compose build` after code changes
- Use `docker-compose logs` to debug issues
- Keep container images lightweight
- Document environment variable changes

### **Error Handling**
- Maintain comprehensive JavaScript null checks
- Use Flask flash messages for user feedback
- Log errors appropriately for debugging
- Test error scenarios thoroughly

---

## 📋 MODIFICATION CHECKLIST

### **Before Starting**
- [ ] Current system is running without errors
- [ ] Backup current database state
- [ ] Document planned changes
- [ ] Identify affected files

### **During Development**
- [ ] Make incremental changes
- [ ] Test frequently with `docker-compose up -d`
- [ ] Check logs for errors: `docker-compose logs web_app`
- [ ] Validate in browser at http://localhost:5002

### **After Changes**
- [ ] All pages load without errors
- [ ] JavaScript console shows no errors
- [ ] Database operations work correctly
- [ ] API endpoints return expected data
- [ ] Update documentation if needed

---

## 🎯 MODIFICATION EXAMPLES

### **Example 1: Add Serial Number Field**

1. **Database Schema** (add to `init/01-create-schema.sql`):
```sql
ALTER TABLE pcb_inventory.tblpcb_inventory 
ADD COLUMN serial_number VARCHAR(50) UNIQUE;
```

2. **Form Update** (in `app.py`):
```python
class StockForm(FlaskForm):
    serial_number = StringField('Serial Number', validators=[DataRequired(), Length(max=50)])
```

3. **Template Update** (in `stock.html`):
```html
<div class="mb-3">
    {{ form.serial_number.label(class="form-label fw-bold") }}
    {{ form.serial_number(class="form-control") }}
</div>
```

### **Example 2: Add Supplier Information Page**

1. **New Route** (in `app.py`):
```python
@app.route('/suppliers')
def suppliers():
    suppliers = db_manager.get_suppliers()  # Implement this method
    return render_template('suppliers.html', suppliers=suppliers)
```

2. **New Template** (`web_app/templates/suppliers.html`):
```html
{% extends "base.html" %}
{% block content %}
<h1>Supplier Management</h1>
<!-- Supplier list and forms here -->
{% endblock %}
```

3. **Navigation Update** (in `base.html`):
```html
<a class="nav-link" href="{{ url_for('suppliers') }}">Suppliers</a>
```

---

**This modification guide provides the essential information needed to confidently make changes to the Stock and Pick PCB Inventory System while maintaining its stability and functionality.**