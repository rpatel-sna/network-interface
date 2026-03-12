-- Network Device Inventory CLI — Database Schema
-- Date: 2026-03-12
-- Target: MariaDB 10.6+
--
-- Tables:
--   devices          Input — operator-managed device registry (tool reads only)
--   device_inventory Output — one current result record per device (tool upserts)

-- ---------------------------------------------------------------------------
-- devices: managed network device registry
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS devices (
    id          INT             NOT NULL AUTO_INCREMENT,
    hostname    VARCHAR(255)    NOT NULL                    COMMENT 'Human-readable label or DNS hostname',
    ip_address  VARCHAR(45)     NOT NULL                    COMMENT 'Management IP (IPv4 or IPv6)',
    ssh_port    INT             NOT NULL DEFAULT 22         COMMENT 'SSH port number',
    username    VARCHAR(255)    NOT NULL                    COMMENT 'SSH authentication username',
    password    VARBINARY(512)  NOT NULL                    COMMENT 'Fernet-encrypted SSH password',
    device_type VARCHAR(64)     NOT NULL                    COMMENT 'Netmiko device_type (e.g. cisco_ios, hp_procurve)',
    enabled     TINYINT(1)      NOT NULL DEFAULT 1          COMMENT '1 = poll on next run; 0 = skip',
    PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- device_inventory: most recent poll result per device
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS device_inventory (
    id               INT          NOT NULL AUTO_INCREMENT,
    device_id        INT          NOT NULL                  COMMENT 'FK to devices.id',
    serial_number    VARCHAR(255) NULL                      COMMENT 'Collected serial number; NULL if not retrieved',
    firmware_version VARCHAR(255) NULL                      COMMENT 'Collected firmware/OS version; NULL if not retrieved',
    last_success     DATETIME     NULL                      COMMENT 'Timestamp of last successful poll; NULL if never succeeded',
    last_attempt     DATETIME     NOT NULL                  COMMENT 'Timestamp of most recent poll attempt',
    status           ENUM('success','failed','timeout')
                                  NOT NULL                  COMMENT 'Result classification for most recent run',
    error_message    TEXT         NULL                      COMMENT 'Error detail or raw output on non-success; NULL on success',
    PRIMARY KEY (id),
    UNIQUE  KEY uq_device_inventory_device_id (device_id),
    CONSTRAINT fk_device_inventory_device
        FOREIGN KEY (device_id)
        REFERENCES devices (id)
        ON DELETE CASCADE
        ON UPDATE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ---------------------------------------------------------------------------
-- Minimal DB user privileges required by the application:
--
--   GRANT SELECT ON <db>.devices TO 'inventory_user'@'%';
--   GRANT INSERT, UPDATE ON <db>.device_inventory TO 'inventory_user'@'%';
-- ---------------------------------------------------------------------------
