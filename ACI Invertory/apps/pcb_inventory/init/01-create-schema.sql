-- Initialize PCB Inventory Database Schema
-- This script creates the initial database structure for the Stock and Pick system

-- Create schema for PCB inventory
CREATE SCHEMA IF NOT EXISTS pcb_inventory;

-- Set search path
SET search_path TO pcb_inventory, public;

-- Create enum for PCB types
CREATE TYPE pcb_type_enum AS ENUM (
    'Bare',
    'Partial', 
    'Completed',
    'Ready to Ship'
);

-- Create enum for location ranges
CREATE TYPE location_range_enum AS ENUM (
    '1000-1999',
    '2000-2999',
    '3000-3999',
    '4000-4999',
    '5000-5999',
    '6000-6999',
    '7000-7999',
    '8000-8999',
    '9000-9999',
    '10000-10999'
);

-- Create the main PCB inventory table
CREATE TABLE IF NOT EXISTS tblPCB_Inventory (
    id SERIAL PRIMARY KEY,
    job VARCHAR(50) NOT NULL,
    pcb_type pcb_type_enum NOT NULL,
    qty INTEGER NOT NULL DEFAULT 0,
    location location_range_enum NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Constraints
    CONSTRAINT qty_non_negative CHECK (qty >= 0),
    CONSTRAINT unique_job_pcb_type UNIQUE (job, pcb_type)
);

-- Create indexes for performance
CREATE INDEX idx_job ON tblPCB_Inventory(job);
CREATE INDEX idx_pcb_type ON tblPCB_Inventory(pcb_type);
CREATE INDEX idx_location ON tblPCB_Inventory(location);
CREATE INDEX idx_job_pcb_type ON tblPCB_Inventory(job, pcb_type);

-- Create audit table for inventory changes
CREATE TABLE IF NOT EXISTS inventory_audit (
    audit_id SERIAL PRIMARY KEY,
    job VARCHAR(50) NOT NULL,
    pcb_type pcb_type_enum NOT NULL,
    operation VARCHAR(10) NOT NULL, -- 'STOCK' or 'PICK'
    quantity_change INTEGER NOT NULL,
    old_quantity INTEGER,
    new_quantity INTEGER,
    location location_range_enum,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    user_id VARCHAR(50) DEFAULT 'system'
);

-- Create function to update the updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Create trigger for updated_at
CREATE TRIGGER update_tblPCB_Inventory_updated_at
    BEFORE UPDATE ON tblPCB_Inventory
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Create function to log inventory changes
CREATE OR REPLACE FUNCTION log_inventory_change()
RETURNS TRIGGER AS $$
BEGIN
    -- Log the change
    INSERT INTO inventory_audit (
        job, pcb_type, operation, quantity_change, 
        old_quantity, new_quantity, location
    )
    VALUES (
        COALESCE(NEW.job, OLD.job),
        COALESCE(NEW.pcb_type, OLD.pcb_type),
        CASE 
            WHEN TG_OP = 'INSERT' THEN 'STOCK'
            WHEN TG_OP = 'UPDATE' AND NEW.qty > OLD.qty THEN 'STOCK'
            WHEN TG_OP = 'UPDATE' AND NEW.qty < OLD.qty THEN 'PICK'
            ELSE 'UPDATE'
        END,
        CASE 
            WHEN TG_OP = 'INSERT' THEN NEW.qty
            WHEN TG_OP = 'UPDATE' THEN NEW.qty - OLD.qty
            WHEN TG_OP = 'DELETE' THEN -OLD.qty
            ELSE 0
        END,
        CASE WHEN TG_OP = 'DELETE' THEN OLD.qty ELSE COALESCE(OLD.qty, 0) END,
        CASE WHEN TG_OP = 'DELETE' THEN 0 ELSE NEW.qty END,
        COALESCE(NEW.location, OLD.location)
    );
    
    RETURN COALESCE(NEW, OLD);
END;
$$ language 'plpgsql';

-- Create trigger for audit logging
CREATE TRIGGER inventory_audit_trigger
    AFTER INSERT OR UPDATE OR DELETE ON tblPCB_Inventory
    FOR EACH ROW
    EXECUTE FUNCTION log_inventory_change();

-- Create views for common queries
CREATE VIEW current_inventory AS
SELECT 
    job,
    pcb_type,
    qty,
    location,
    created_at,
    updated_at
FROM tblPCB_Inventory
WHERE qty > 0;

CREATE VIEW inventory_summary AS
SELECT 
    pcb_type,
    COUNT(*) as job_count,
    SUM(qty) as total_quantity,
    AVG(qty) as average_quantity,
    location
FROM tblPCB_Inventory
WHERE qty > 0
GROUP BY pcb_type, location
ORDER BY pcb_type, location;

-- Create stored procedures for common operations
CREATE OR REPLACE FUNCTION stock_pcb(
    p_job VARCHAR(50),
    p_pcb_type pcb_type_enum,
    p_qty INTEGER,
    p_location location_range_enum
) RETURNS JSON AS $$
DECLARE
    v_old_qty INTEGER := 0;
    v_new_qty INTEGER;
    v_result JSON;
BEGIN
    -- Check if record exists
    SELECT qty INTO v_old_qty 
    FROM tblPCB_Inventory 
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    IF v_old_qty IS NULL THEN
        -- Create new record
        INSERT INTO tblPCB_Inventory (job, pcb_type, qty, location)
        VALUES (p_job, p_pcb_type, p_qty, p_location);
        v_new_qty := p_qty;
    ELSE
        -- Update existing record
        v_new_qty := v_old_qty + p_qty;
        UPDATE tblPCB_Inventory 
        SET qty = v_new_qty, location = p_location
        WHERE job = p_job AND pcb_type = p_pcb_type;
    END IF;
    
    -- Return result
    v_result := json_build_object(
        'success', true,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'old_qty', COALESCE(v_old_qty, 0),
        'new_qty', v_new_qty,
        'stocked_qty', p_qty,
        'location', p_location
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE FUNCTION pick_pcb(
    p_job VARCHAR(50),
    p_pcb_type pcb_type_enum,
    p_qty INTEGER
) RETURNS JSON AS $$
DECLARE
    v_old_qty INTEGER := 0;
    v_new_qty INTEGER;
    v_result JSON;
BEGIN
    -- Check if record exists and get current quantity
    SELECT qty INTO v_old_qty 
    FROM tblPCB_Inventory 
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    IF v_old_qty IS NULL THEN
        -- Job not found
        v_result := json_build_object(
            'success', false,
            'error', 'Job not found',
            'job', p_job,
            'pcb_type', p_pcb_type
        );
        RETURN v_result;
    END IF;
    
    -- Check if enough quantity available
    IF v_old_qty < p_qty THEN
        v_result := json_build_object(
            'success', false,
            'error', 'Insufficient quantity',
            'job', p_job,
            'pcb_type', p_pcb_type,
            'available_qty', v_old_qty,
            'requested_qty', p_qty
        );
        RETURN v_result;
    END IF;
    
    -- Update quantity
    v_new_qty := v_old_qty - p_qty;
    UPDATE tblPCB_Inventory 
    SET qty = v_new_qty
    WHERE job = p_job AND pcb_type = p_pcb_type;
    
    -- Return success result
    v_result := json_build_object(
        'success', true,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'old_qty', v_old_qty,
        'new_qty', v_new_qty,
        'picked_qty', p_qty
    );
    
    RETURN v_result;
END;
$$ LANGUAGE plpgsql;

-- Insert some sample data for testing
INSERT INTO tblPCB_Inventory (job, pcb_type, qty, location) VALUES
    ('12345', 'Bare', 100, '8000-8999'),
    ('12345', 'Partial', 50, '8000-8999'),
    ('12346', 'Bare', 200, '7000-7999'),
    ('12347', 'Completed', 25, '9000-9999'),
    ('12348', 'Ready to Ship', 10, '10000-10999')
ON CONFLICT (job, pcb_type) DO NOTHING;

-- Grant permissions
GRANT ALL PRIVILEGES ON SCHEMA pcb_inventory TO stockpick_user;
GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA pcb_inventory TO stockpick_user;
GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA pcb_inventory TO stockpick_user;
GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pcb_inventory TO stockpick_user;