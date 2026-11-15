-- PostGIS and the firms schema (web database design, 6.1).
--
-- PostGIS is not a trusted extension: when the database lacks it, a superuser creates it once (the PostGIS image
-- of the application does it for its database). The rest of the package runs as the owner of the database.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS firms;
