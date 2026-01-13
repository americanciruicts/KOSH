-- Stock and Pick Stored Procedures for PCB Inventory System
-- Created: 2025-10-28
-- Purpose: Handle stock and pick operations with proper transaction logging

-- ============================================================================
-- STOCK PCB FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION pcb_inventory.stock_pcb(
    p_job VARCHAR(255),
    p_pcb_type VARCHAR(255),
    p_quantity INTEGER,
    p_location_from VARCHAR(255),
    p_location_to VARCHAR(255),
    p_itar_classification VARCHAR(50) DEFAULT 'NONE',
    p_user_role VARCHAR(50) DEFAULT 'USER',
    p_itar_auth BOOLEAN DEFAULT FALSE,
    p_username VARCHAR(255) DEFAULT 'system',
    p_pcn INTEGER DEFAULT NULL,
    p_work_order TEXT DEFAULT NULL,
    p_dc VARCHAR(255) DEFAULT NULL,
    p_msd VARCHAR(255) DEFAULT NULL,
    p_mpn VARCHAR(255) DEFAULT NULL,
    p_part_number VARCHAR(255) DEFAULT NULL
) RETURNS JSON AS $$
DECLARE
    v_existing_id INTEGER;
    v_existing_qty INTEGER;
    v_new_qty INTEGER;
    v_pcn INTEGER;
    v_result JSON;
BEGIN
    -- Validate required fields
    IF p_job IS NULL OR p_job = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Job number is required'
        );
    END IF;

    IF p_pcb_type IS NULL OR p_pcb_type = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'PCB type is required'
        );
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Quantity must be greater than 0'
        );
    END IF;

    IF p_location_from IS NULL OR p_location_from = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Location From is required'
        );
    END IF;

    IF p_location_to IS NULL OR p_location_to = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Location To is required'
        );
    END IF;

    -- Generate PCN if not provided
    IF p_pcn IS NULL THEN
        v_pcn := pcb_inventory.generate_pcn_number();
    ELSE
        v_pcn := p_pcn;
    END IF;

    -- Check if inventory item already exists (match by job and pcb_type)
    SELECT id, qty INTO v_existing_id, v_existing_qty
    FROM pcb_inventory."tblPCB_Inventory"
    WHERE job = p_job AND pcb_type = p_pcb_type
    LIMIT 1;

    IF v_existing_id IS NOT NULL THEN
        -- Update existing inventory
        v_new_qty := COALESCE(v_existing_qty, 0) + p_quantity;

        UPDATE pcb_inventory."tblPCB_Inventory"
        SET
            qty = v_new_qty,
            location = p_location_to,
            pcn = COALESCE(p_pcn, pcn, v_pcn),
            migrated_at = CURRENT_TIMESTAMP
        WHERE id = v_existing_id;
    ELSE
        -- Insert new inventory record
        v_new_qty := p_quantity;

        INSERT INTO pcb_inventory."tblPCB_Inventory" (
            pcn, job, pcb_type, qty, location, migrated_at
        ) VALUES (
            v_pcn, p_job, p_pcb_type, p_quantity, p_location_to, CURRENT_TIMESTAMP
        );

        v_existing_id := currval('pcb_inventory."tblPCB_Inventory_id_seq"');
    END IF;

    -- Log transaction with location tracking (convert dc to integer if possible, otherwise NULL)
    INSERT INTO pcb_inventory."tblTransaction" (
        trantype, item, pcn, mpn, dc, tranqty, loc_from, loc_to, wo, po, userid, migrated_at
    ) VALUES (
        'STOCK',
        p_job,
        v_pcn,
        p_mpn,
        CASE WHEN p_dc ~ '^\d+$' THEN p_dc::INTEGER ELSE NULL END,
        p_quantity,
        p_location_from,
        p_location_to,
        p_work_order,
        NULL,
        p_username,
        CURRENT_TIMESTAMP
    );

    -- Return success result
    v_result := json_build_object(
        'success', TRUE,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'stocked_qty', p_quantity,
        'new_qty', v_new_qty,
        'location', p_location,
        'pcn', v_pcn,
        'message', format('Successfully stocked %s %s PCBs for job %s', p_quantity, p_pcb_type, p_job)
    );

    RETURN v_result;

EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object(
        'success', FALSE,
        'error', format('Stock operation failed: %s', SQLERRM)
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- PICK PCB FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION pcb_inventory.pick_pcb(
    p_job VARCHAR(255),
    p_pcb_type VARCHAR(255),
    p_quantity INTEGER,
    p_user_role VARCHAR(50) DEFAULT 'USER',
    p_itar_auth BOOLEAN DEFAULT FALSE,
    p_username VARCHAR(255) DEFAULT 'system',
    p_work_order TEXT DEFAULT NULL
) RETURNS JSON AS $$
DECLARE
    v_existing_id INTEGER;
    v_existing_qty INTEGER;
    v_new_qty INTEGER;
    v_location VARCHAR(255);
    v_pcn INTEGER;
    v_result JSON;
BEGIN
    -- Validate required fields
    IF p_job IS NULL OR p_job = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Job number is required'
        );
    END IF;

    IF p_pcb_type IS NULL OR p_pcb_type = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'PCB type is required'
        );
    END IF;

    IF p_quantity IS NULL OR p_quantity <= 0 THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Quantity must be greater than 0'
        );
    END IF;

    -- Check if inventory item exists
    SELECT id, qty, location, pcn
    INTO v_existing_id, v_existing_qty, v_location, v_pcn
    FROM pcb_inventory."tblPCB_Inventory"
    WHERE job = p_job AND pcb_type = p_pcb_type
    LIMIT 1;

    IF v_existing_id IS NULL THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', format('Job %s with PCB type %s not found in inventory', p_job, p_pcb_type),
            'job', p_job,
            'pcb_type', p_pcb_type
        );
    END IF;

    -- Check if sufficient quantity available
    IF COALESCE(v_existing_qty, 0) < p_quantity THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Insufficient quantity available',
            'available_qty', COALESCE(v_existing_qty, 0),
            'requested_qty', p_quantity,
            'job', p_job,
            'pcb_type', p_pcb_type
        );
    END IF;

    -- Calculate new quantity
    v_new_qty := v_existing_qty - p_quantity;

    -- Update inventory
    IF v_new_qty = 0 THEN
        -- Remove item from inventory if quantity reaches 0
        DELETE FROM pcb_inventory."tblPCB_Inventory"
        WHERE id = v_existing_id;
    ELSE
        -- Update quantity and timestamp
        UPDATE pcb_inventory."tblPCB_Inventory"
        SET
            qty = v_new_qty,
            migrated_at = CURRENT_TIMESTAMP
        WHERE id = v_existing_id;
    END IF;

    -- Log transaction
    INSERT INTO pcb_inventory."tblTransaction" (
        trantype, item, pcn, tranqty, loc_from, wo, userid, migrated_at
    ) VALUES (
        'PICK',
        p_job,
        v_pcn,
        p_quantity,
        v_location,
        p_work_order,
        p_username,
        CURRENT_TIMESTAMP
    );

    -- Return success result
    v_result := json_build_object(
        'success', TRUE,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'picked_qty', p_quantity,
        'new_qty', v_new_qty,
        'location', v_location,
        'message', format('Successfully picked %s %s PCBs for job %s. Remaining: %s',
                         p_quantity, p_pcb_type, p_job, v_new_qty)
    );

    RETURN v_result;

EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object(
        'success', FALSE,
        'error', format('Pick operation failed: %s', SQLERRM)
    );
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- UPDATE INVENTORY FUNCTION
-- ============================================================================
CREATE OR REPLACE FUNCTION pcb_inventory.update_inventory(
    p_id INTEGER,
    p_job VARCHAR(255),
    p_pcb_type VARCHAR(255),
    p_quantity INTEGER,
    p_location VARCHAR(255),
    p_pcn INTEGER DEFAULT NULL,
    p_username VARCHAR(255) DEFAULT 'system'
) RETURNS JSON AS $$
DECLARE
    v_old_job VARCHAR(255);
    v_old_pcb_type VARCHAR(255);
    v_old_qty INTEGER;
    v_old_location VARCHAR(255);
    v_old_pcn INTEGER;
    v_result JSON;
BEGIN
    -- Validate required fields
    IF p_id IS NULL THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Inventory ID is required'
        );
    END IF;

    IF p_job IS NULL OR p_job = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Job number is required'
        );
    END IF;

    IF p_pcb_type IS NULL OR p_pcb_type = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'PCB type is required'
        );
    END IF;

    IF p_quantity IS NULL OR p_quantity < 0 THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Quantity must be 0 or greater'
        );
    END IF;

    IF p_location IS NULL OR p_location = '' THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', 'Location is required'
        );
    END IF;

    -- Get old values for audit trail
    SELECT job, pcb_type, qty, location, pcn
    INTO v_old_job, v_old_pcb_type, v_old_qty, v_old_location, v_old_pcn
    FROM pcb_inventory."tblPCB_Inventory"
    WHERE id = p_id;

    IF NOT FOUND THEN
        RETURN json_build_object(
            'success', FALSE,
            'error', format('Inventory item with ID %s not found', p_id)
        );
    END IF;

    -- Update the inventory record
    UPDATE pcb_inventory."tblPCB_Inventory"
    SET
        job = p_job,
        pcb_type = p_pcb_type,
        qty = p_quantity,
        location = p_location,
        pcn = COALESCE(p_pcn, pcn),
        migrated_at = CURRENT_TIMESTAMP
    WHERE id = p_id;

    -- Log the update as a NEW transaction (historical transactions remain unchanged)
    -- This preserves audit trail integrity - old transactions show what actually happened
    INSERT INTO pcb_inventory."tblTransaction" (
        trantype, item, pcn, tranqty, loc_from, loc_to, userid, migrated_at
    ) VALUES (
        'UPDATE',
        p_job,
        COALESCE(p_pcn, v_old_pcn),
        p_quantity - v_old_qty,  -- Change in quantity
        v_old_location,
        p_location,
        p_username,
        CURRENT_TIMESTAMP
    );

    -- Return success result with before/after details
    v_result := json_build_object(
        'success', TRUE,
        'id', p_id,
        'job', p_job,
        'pcb_type', p_pcb_type,
        'quantity', p_quantity,
        'location', p_location,
        'pcn', COALESCE(p_pcn, v_old_pcn),
        'old_values', json_build_object(
            'job', v_old_job,
            'pcb_type', v_old_pcb_type,
            'quantity', v_old_qty,
            'location', v_old_location
        ),
        'message', format('Successfully updated inventory item %s', p_id)
    );

    RETURN v_result;

EXCEPTION WHEN OTHERS THEN
    RETURN json_build_object(
        'success', FALSE,
        'error', format('Update operation failed: %s', SQLERRM)
    );
END;
$$ LANGUAGE plpgsql;

-- Grant execute permissions
GRANT EXECUTE ON FUNCTION pcb_inventory.stock_pcb TO stockpick_user;
GRANT EXECUTE ON FUNCTION pcb_inventory.pick_pcb TO stockpick_user;
GRANT EXECUTE ON FUNCTION pcb_inventory.update_inventory TO stockpick_user;

-- Success message
SELECT 'Stock, Pick, and Update procedures created successfully!' as status;
