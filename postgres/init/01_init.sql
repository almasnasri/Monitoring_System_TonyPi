-- =============================================================================
-- PostgreSQL Database Initialization Script
-- TonyPi Robot Monitoring System
-- =============================================================================
--
-- This script initializes the PostgreSQL database with all required tables
-- for the TonyPi monitoring system. It runs automatically when the PostgreSQL
-- Docker container starts for the first time.
--
-- DATABASE SCHEMA OVERVIEW:
--   ┌─────────────┐     ┌─────────────────┐     ┌─────────────┐
--   │   robots    │     │  robot_configs  │     │   reports   │
--   │─────────────│     │─────────────────│     │─────────────│
--   │ robot_id PK │◄────│ robot_id FK     │     │ robot_id    │
--   │ name        │     │ config_type     │     │ report_type │
--   │ status      │     │ config_data     │     │ data (JSON) │
--   └─────────────┘     └─────────────────┘     └─────────────┘
--          │
--          │          ┌─────────────┐     ┌─────────────────┐
--          └─────────►│  commands   │     │   system_logs   │
--                     │─────────────│     │─────────────────│
--                     │ robot_id FK │     │ level           │
--                     │ command     │     │ message         │
--                     │ status      │     │ source          │
--                     └─────────────┘     └─────────────────┘
--
--                     ┌─────────────┐
--                     │    users    │
--                     │─────────────│
--                     │ username    │
--                     │ password    │  (hashed with bcrypt)
--                     │ role        │  (admin/operator/viewer)
--                     └─────────────┘
--
-- NOTE: This is a LEGACY initialization script. The actual tables are now
-- managed by SQLAlchemy ORM models in backend/models/. This script provides
-- a fallback and reference for the database schema.
--
-- EXECUTION:
--   This script runs once when the PostgreSQL container is first created.
--   It's mounted via docker-compose.yml:
--     volumes:
--       - ./postgres/init:/docker-entrypoint-initdb.d
-- =============================================================================

-- Connect to the database (created by POSTGRES_DB env variable)
\c tonypi_db;

-- =============================================================================
-- EXTENSIONS
-- =============================================================================

-- Enable UUID generation for primary keys
-- uuid_generate_v4() creates random UUIDs (version 4)
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- =============================================================================
-- ROBOTS TABLE
-- =============================================================================
-- Stores information about each registered TonyPi robot.
-- Robots are automatically registered when they first connect via MQTT.
--
-- COLUMNS:
--   id         - Internal UUID (for foreign keys)
--   robot_id   - Unique human-readable identifier (e.g., "tonypi_raspberrypi")
--   name       - Display name for the robot
--   robot_type - Hardware type (default: HiWonder TonyPi)
--   status     - Current connection status (online/offline/idle/busy)
--   created_at - When robot was first registered
--   updated_at - Last modification timestamp
--
CREATE TABLE IF NOT EXISTS robots (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id VARCHAR(50) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    robot_type VARCHAR(50) DEFAULT 'HiWonder TonyPi',
    status VARCHAR(20) DEFAULT 'offline',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Robot configurations table
CREATE TABLE IF NOT EXISTS robot_configs (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    robot_id VARCHAR(50) REFERENCES robots(robot_id) ON DELETE CASCADE,
    config_type VARCHAR(50) NOT NULL,
    config_data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Reports table
CREATE TABLE IF NOT EXISTS reports (
    id SERIAL PRIMARY KEY,
    title VARCHAR(200) NOT NULL,
    description TEXT,
    robot_id VARCHAR(50),
    report_type VARCHAR(50) NOT NULL,
    data JSONB,
    file_path VARCHAR(500),
    created_by VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Commands table
CREATE TABLE IF NOT EXISTS commands (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    command_id VARCHAR(100) UNIQUE NOT NULL,
    robot_id VARCHAR(50) REFERENCES robots(robot_id) ON DELETE CASCADE,
    command VARCHAR(100) NOT NULL,
    parameters JSONB,
    status VARCHAR(20) DEFAULT 'pending',
    response JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    executed_at TIMESTAMP
);

-- Users table (for future authentication)
CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    username VARCHAR(50) UNIQUE NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- System logs table
CREATE TABLE IF NOT EXISTS system_logs (
    id SERIAL PRIMARY KEY,
    level VARCHAR(20) NOT NULL,
    message TEXT NOT NULL,
    source VARCHAR(100),
    data JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default robot
INSERT INTO robots (robot_id, name, status) 
VALUES ('tonypi_01', 'TonyPi Robot 01', 'offline')
ON CONFLICT (robot_id) DO NOTHING;

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_robots_status ON robots(status);
CREATE INDEX IF NOT EXISTS idx_reports_robot_id ON reports(robot_id);
CREATE INDEX IF NOT EXISTS idx_reports_created_at ON reports(created_at);
CREATE INDEX IF NOT EXISTS idx_commands_robot_id ON commands(robot_id);
CREATE INDEX IF NOT EXISTS idx_commands_status ON commands(status);
CREATE INDEX IF NOT EXISTS idx_system_logs_level ON system_logs(level);
CREATE INDEX IF NOT EXISTS idx_system_logs_created_at ON system_logs(created_at);

-- Insert sample reports
INSERT INTO reports (title, description, robot_id, report_type, data) VALUES
('Daily Performance Report', 'Automated daily performance summary for TonyPi Robot 01', 'tonypi_01', 'performance', '{"uptime": "23h 45m", "tasks_completed": 15, "errors": 0}'),
('Battery Health Report', 'Weekly battery health analysis for TonyPi Robot 01', 'tonypi_01', 'battery', '{"avg_voltage": 12.3, "discharge_cycles": 45, "health": "Good"}')
ON CONFLICT DO NOTHING;