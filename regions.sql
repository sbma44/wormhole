DROP TABLE IF EXISTS regions;
CREATE TABLE regions (
	name VARCHAR(36) NOT NULL, 
	short_name VARCHAR(10) NOT NULL, 
	id VARCHAR(14) NOT NULL, 
	domain VARCHAR(32) NOT NULL, 
	connection_type VARCHAR(14) NOT NULL, 
	ami_id VARCHAR(12), 
	lat REAL NOT NULL, 
	lon REAL NOT NULL
);