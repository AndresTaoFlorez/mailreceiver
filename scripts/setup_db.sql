-- Run as postgres superuser:
--   sudo -u postgres psql -f setup_db.sql

CREATE USER mailreceiver WITH PASSWORD 'mailreceiver';
CREATE DATABASE mailreceiver OWNER mailreceiver;

-- Connect to the new database and grant permissions
\c mailreceiver
GRANT ALL PRIVILEGES ON SCHEMA public TO mailreceiver;
